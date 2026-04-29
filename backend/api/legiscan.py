"""
Legiscan API wrapper — state legislators, bills, and sessions.

Free tier is 30k requests/month + 1 req/sec, so we lean on ai_cache heavily.
All Legiscan ops are GETs against https://api.legiscan.com/?key=KEY&op=NAME.

Public functions:
  - get_state_legislators(state)        -> list[dict]   (normalized)
  - search_state_legislators(state, q)  -> list[dict]   (filters cached roster)
  - get_legislator(people_id)           -> dict | None  (profile + sponsored bills)
  - get_legislator_votes(people_id)     -> list[dict]   (recent roll calls)

Falls back to SAMPLE_STATE_LEGISLATORS when no API key is set or the
upstream request fails, matching the rest of backend/api/*.
"""
import asyncio
import httpx

from config import LEGISCAN_API_KEY, LEGISCAN_BASE
from api import ai_cache

_TIMEOUT = 15.0

# 7-day TTL: state legislators + sessions barely move mid-session.
_LIST_TTL_HOURS = 24 * 7
# 24-hour TTL: sponsored bills update over time within a session.
_PROFILE_TTL_HOURS = 24
# 24-hour TTL: roll calls for a rep rarely change intra-day and vote fetching
# is the most expensive Legiscan path (~2 calls per bill).
_VOTES_TTL_HOURS = 24
# How many of the rep's most-recent sponsored bills to probe for roll calls.
_VOTES_BILL_LIMIT = 8


# ---- Sample data for offline/no-key dev ---------------------------

SAMPLE_STATE_LEGISLATORS = {
    "CT": [
        {
            "people_id": 9001,
            "name": "Martin M. Looney",
            "first_name": "Martin",
            "last_name": "Looney",
            "party": "D",
            "role": "Sen",
            "district": "SD-11",
            "state": "CT",
            "chamber": "Senate",
            "ftm_eid": None,
        },
        {
            "people_id": 9002,
            "name": "Matt Ritter",
            "first_name": "Matt",
            "last_name": "Ritter",
            "party": "D",
            "role": "Rep",
            "district": "HD-1",
            "state": "CT",
            "chamber": "House",
            "ftm_eid": None,
        },
        {
            "people_id": 9003,
            "name": "Vincent Candelora",
            "first_name": "Vincent",
            "last_name": "Candelora",
            "party": "R",
            "role": "Rep",
            "district": "HD-86",
            "state": "CT",
            "chamber": "House",
            "ftm_eid": None,
        },
    ]
}

SAMPLE_LEGISLATOR_PROFILE = {
    9001: {
        "people_id": 9001,
        "name": "Martin M. Looney",
        "first_name": "Martin",
        "last_name": "Looney",
        "party": "D",
        "role": "Sen",
        "district": "SD-11",
        "state": "CT",
        "chamber": "Senate",
        "sponsored_bills": [
            {"bill_id": 1800001, "number": "SB-1", "title": "An Act Concerning Affordable Housing", "status": "Introduced"},
            {"bill_id": 1800002, "number": "SB-24", "title": "An Act Expanding Paid Family Medical Leave", "status": "Passed"},
        ],
    }
}


# ---- HTTP helpers -------------------------------------------------

async def _call(op: str, **params) -> dict:
    """Raw Legiscan GET. Returns the parsed JSON payload or raises."""
    if not LEGISCAN_API_KEY:
        raise RuntimeError("LEGISCAN_API_KEY not set")
    q = {"key": LEGISCAN_API_KEY, "op": op, **params}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(LEGISCAN_BASE, params=q)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"legiscan {op} returned status={data.get('status')}: {data.get('alert')}")
    return data


# ---- Normalization -----------------------------------------------

_ROLE_TO_CHAMBER = {
    "Sen": "Senate",
    "Senator": "Senate",
    "Rep": "House",
    "Representative": "House",
}


def _normalize_person(p: dict, state: str) -> dict:
    role = p.get("role") or p.get("role_abbr") or ""
    chamber = _ROLE_TO_CHAMBER.get(role, "")
    district = p.get("district") or ""
    # Legiscan district fields are sometimes just a number like "011" —
    # combine with role abbreviation for a readable label (e.g. "SD-11").
    if district and not any(c.isalpha() for c in district):
        prefix = "SD" if chamber == "Senate" else "HD" if chamber == "House" else "D"
        district = f"{prefix}-{district.lstrip('0') or '0'}"
    return {
        "people_id": p.get("people_id"),
        "name": p.get("name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
        "first_name": p.get("first_name", ""),
        "last_name": p.get("last_name", ""),
        "party": p.get("party", ""),
        "role": role,
        "district": district,
        "state": state.upper(),
        "chamber": chamber,
        "ftm_eid": p.get("ftm_eid"),
    }


# ---- Public API ---------------------------------------------------

async def get_state_legislators(state: str) -> list[dict]:
    """
    Return the current-session state legislators for `state` (e.g. "CT").
    Uses the most recent session from getSessionList, then getSessionPeople.
    Cached in ai_cache for 7 days.
    """
    state = state.upper()
    cache_key = f"legiscan:people:{state}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    if not LEGISCAN_API_KEY:
        return list(SAMPLE_STATE_LEGISLATORS.get(state, []))

    try:
        sessions_data = await _call("getSessionList", state=state)
        sessions = sessions_data.get("sessions") or []
        if not sessions:
            return list(SAMPLE_STATE_LEGISLATORS.get(state, []))
        # Legiscan returns sessions newest-first; fall back to max session_id.
        current = max(sessions, key=lambda s: s.get("session_id", 0))
        session_id = current["session_id"]

        people_data = await _call("getSessionPeople", id=session_id)
        raw = (people_data.get("sessionpeople") or {}).get("people") or []
        results = [_normalize_person(p, state) for p in raw]
        # Sort by chamber then district for stable ordering.
        results.sort(key=lambda r: (r["chamber"], r["district"]))
        ai_cache.set(cache_key, results, ttl_hours=_LIST_TTL_HOURS)
        print(f"[legiscan] {state}: {len(results)} legislators from session {session_id}")
        return results
    except Exception as e:
        print(f"[legiscan] {state} unavailable ({e}), using sample data")
        return list(SAMPLE_STATE_LEGISLATORS.get(state, []))


async def search_state_legislators(state: str, query: str) -> list[dict]:
    """
    Filter the cached roster for `state` by name substring. Reuses
    get_state_legislators(), so no extra Legiscan calls when the roster
    is already cached.
    """
    if not state or not query or len(query) < 2:
        return []
    roster = await get_state_legislators(state)
    q = query.lower()
    return [
        r for r in roster
        if q in (r.get("name") or "").lower()
        or q in (r.get("last_name") or "").lower()
    ]


async def get_legislator(people_id: int) -> dict | None:
    """
    Return profile + recent sponsored bills for a state legislator.
    Cached for 24 hours.
    """
    try:
        people_id = int(people_id)
    except (TypeError, ValueError):
        return None

    cache_key = f"legiscan:profile:{people_id}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    if not LEGISCAN_API_KEY:
        return SAMPLE_LEGISLATOR_PROFILE.get(people_id)

    try:
        person_data = await _call("getPerson", id=people_id)
        person = person_data.get("person") or {}
        if not person:
            return None

        state = person.get("state", "")
        profile = _normalize_person(person, state)

        sponsored: list[dict] = []
        try:
            sponsored_data = await _call("getSponsoredList", id=people_id)
            sb = sponsored_data.get("sponsoredbills") or {}
            # Legiscan returns `bills` as a flat list with session_id on each
            # entry, alongside a sibling `sessions` list of session metadata.
            # Newest-first by session_id, with bill_id as tiebreaker.
            raw_bills = sorted(
                sb.get("bills") or [],
                key=lambda b: (b.get("session_id", 0), b.get("bill_id", 0)),
                reverse=True,
            )
            for b in raw_bills[:15]:
                sponsored.append({
                    "bill_id": b.get("bill_id"),
                    "number": b.get("number") or b.get("bill_number", ""),
                    "title": b.get("title", ""),
                    "status": b.get("status_desc") or b.get("status", ""),
                })
        except Exception as e:
            print(f"[legiscan] sponsored lookup for {people_id} failed ({e})")

        profile["sponsored_bills"] = sponsored
        ai_cache.set(cache_key, profile, ttl_hours=_PROFILE_TTL_HOURS)
        return profile
    except Exception as e:
        print(f"[legiscan] person {people_id} unavailable ({e})")
        return SAMPLE_LEGISLATOR_PROFILE.get(people_id)


async def get_legislator_votes(people_id: int) -> list[dict]:
    """
    Return recent roll-call votes for a state legislator, normalized to the
    same shape as federal votes (title/date/member_vote/category) so the
    shared formatters in api.congress_gov can consume them.

    Strategy: fetch bill detail for the rep's most recent sponsored bills,
    pick the latest roll call on each, and record how this legislator voted.
    Cached 24h. Returns [] when no key, no bills, or on upstream failure.
    """
    try:
        people_id = int(people_id)
    except (TypeError, ValueError):
        return []

    cache_key = f"legiscan:votes:{people_id}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    if not LEGISCAN_API_KEY:
        return []

    profile = await get_legislator(people_id)
    if not profile:
        return []

    sponsored = [b for b in (profile.get("sponsored_bills") or []) if b.get("bill_id")]
    sponsored = sponsored[:_VOTES_BILL_LIMIT]
    if not sponsored:
        ai_cache.set(cache_key, [], ttl_hours=_VOTES_TTL_HOURS)
        return []

    async def _bill(bill_id: int) -> dict:
        try:
            data = await _call("getBill", id=bill_id)
            return data.get("bill") or {}
        except Exception as e:
            print(f"[legiscan] getBill({bill_id}) failed ({e})")
            return {}

    bill_details = await asyncio.gather(*[_bill(b["bill_id"]) for b in sponsored])

    # For each bill with roll calls, take the newest one and record which
    # roll-call id maps to which bill title.
    rc_ids: list[int] = []
    rc_meta: dict[int, tuple[str, str, str]] = {}
    for bill in bill_details:
        rc_list = bill.get("votes") or []
        if not rc_list:
            continue
        rc = max(rc_list, key=lambda r: r.get("date", ""))
        rc_id = rc.get("roll_call_id")
        if not rc_id:
            continue
        rc_meta[rc_id] = (
            bill.get("title", ""),
            rc.get("date", ""),
            rc.get("chamber", ""),
        )
        rc_ids.append(rc_id)

    if not rc_ids:
        ai_cache.set(cache_key, [], ttl_hours=_VOTES_TTL_HOURS)
        return []

    async def _roll_call(rc_id: int) -> dict:
        try:
            data = await _call("getRollCall", id=rc_id)
            return data.get("roll_call") or {}
        except Exception as e:
            print(f"[legiscan] getRollCall({rc_id}) failed ({e})")
            return {}

    roll_calls = await asyncio.gather(*[_roll_call(rc_id) for rc_id in rc_ids])

    results: list[dict] = []
    for rc_id, rc in zip(rc_ids, roll_calls):
        my_vote = next(
            (v for v in (rc.get("votes") or []) if v.get("people_id") == people_id),
            None,
        )
        if not my_vote:
            continue
        title, date, chamber = rc_meta[rc_id]
        results.append({
            "title": title,
            "date": date or rc.get("date", ""),
            "member_vote": my_vote.get("vote_text", ""),
            "category": chamber or rc.get("chamber", ""),
        })

    results.sort(key=lambda r: r.get("date", ""), reverse=True)
    ai_cache.set(cache_key, results, ttl_hours=_VOTES_TTL_HOURS)
    print(f"[legiscan] votes for {people_id}: {len(results)} roll calls")
    return results
