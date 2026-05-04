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
from alerts.state_categories import categorize as _categorize_title

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
# 6-hour TTL: master list (active bills) shifts within a session as bills
# advance through chambers, but not so fast that intra-day refresh is needed.
_BILLS_TTL_HOURS = 6

# Bill status codes: see Legiscan docs.
# We treat "engrossed" (passed one chamber) as the imminent-vote signal.
STATUS_INTRODUCED = 1
STATUS_ENGROSSED = 2
STATUS_ENROLLED = 3
STATUS_PASSED = 4
STATUS_VETOED = 5
STATUS_FAILED = 6
IMMINENT_VOTE_STATUSES = {STATUS_ENGROSSED}  # add STATUS_ENROLLED later if needed


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

SAMPLE_ACTIVE_BILLS = {
    "CT": [
        {
            "bill_id": 1900001,
            "number": "SB-1",
            "title": "An Act Concerning Affordable Housing And Tenant Protections",
            "description": "Expands rental assistance and caps annual rent increases for buildings over 30 units.",
            "status": 2,                     # 2 = engrossed: passed one chamber
            "status_date": None,             # filled at sample-load time
            "last_action": "Passed in Senate, sent to House",
            "chamber": "Senate",
        },
        {
            "bill_id": 1900002,
            "number": "HB-5485",
            "title": "An Act Concerning Pharmaceutical Drug Pricing Transparency",
            "description": "Requires drug manufacturers to disclose price increases over 25% in any 12-month period.",
            "status": 2,
            "status_date": None,
            "last_action": "Passed in House, referred to Senate",
            "chamber": "House",
        },
        {
            "bill_id": 1900003,
            "number": "SB-872",
            "title": "An Act Concerning Climate Change And Renewable Energy Standards",
            "description": "Sets a 100% zero-carbon electricity standard by 2040.",
            "status": 2,
            "status_date": None,
            "last_action": "Passed in Senate, sent to House",
            "chamber": "Senate",
        },
        {
            "bill_id": 1900004,
            "number": "HB-6618",
            "title": "An Act Concerning State University Tuition And Student Loans",
            "description": "Caps tuition increases and creates a low-interest student loan refinancing program.",
            "status": 1,                     # introduced — too early to alert
            "status_date": None,
            "last_action": "Referred to Joint Committee on Higher Education",
            "chamber": "House",
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
            "category": _categorize_title(title) or "",
            "chamber": chamber or rc.get("chamber", ""),
        })

    results.sort(key=lambda r: r.get("date", ""), reverse=True)
    ai_cache.set(cache_key, results, ttl_hours=_VOTES_TTL_HOURS)
    print(f"[legiscan] votes for {people_id}: {len(results)} roll calls")
    return results


# ---- Active bills (master list) -----------------------------------

def _normalize_bill(b: dict) -> dict:
    """Reduce a Legiscan masterlist row to the fields the alerts pipeline needs."""
    status = b.get("status")
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    return {
        "bill_id": b.get("bill_id"),
        "number": b.get("number") or b.get("bill_number") or "",
        "title": b.get("title") or "",
        "description": b.get("description") or "",
        "status": status,
        "status_date": b.get("status_date") or b.get("last_action_date") or "",
        "last_action": b.get("last_action") or "",
        "last_action_date": b.get("last_action_date") or "",
        # masterlist doesn't include chamber, but body code (H/S) is sometimes
        # in `body` or inferable from the bill number prefix.
        "chamber": _infer_chamber(b),
    }


def _infer_chamber(b: dict) -> str:
    """Pick a chamber for a Legiscan bill row from whatever fields are present."""
    body = (b.get("body") or "").upper()
    if body in ("H", "A"):
        return "House"
    if body == "S":
        return "Senate"
    number = (b.get("number") or b.get("bill_number") or "").upper()
    if number.startswith(("HB", "HR", "AB")):
        return "House"
    if number.startswith(("SB", "SR")):
        return "Senate"
    return ""


async def get_active_bills(state: str) -> list[dict]:
    """
    Return bills in the state's current session that are at "imminent vote"
    status (engrossed = passed one chamber, headed to the other).

    The Legiscan masterlist for a session can be hundreds to thousands of
    bills; we filter to STATUS_ENGROSSED here to keep downstream classification
    cheap. Cached 6h via ai_cache. Falls back to SAMPLE_ACTIVE_BILLS when no
    key is set or the upstream fails.
    """
    state = state.upper()
    cache_key = f"legiscan:active_bills:{state}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    if not LEGISCAN_API_KEY:
        return _sample_active_bills(state)

    try:
        sessions_data = await _call("getSessionList", state=state)
        sessions = sessions_data.get("sessions") or []
        if not sessions:
            return _sample_active_bills(state)
        current = max(sessions, key=lambda s: s.get("session_id", 0))
        session_id = current["session_id"]

        master_data = await _call("getMasterList", id=session_id)
        masterlist = master_data.get("masterlist") or {}
        # Legiscan returns the masterlist as numeric-string-keyed dicts plus a
        # "session" key with metadata; iterate entries that look like bills.
        rows = [v for k, v in masterlist.items() if k != "session" and isinstance(v, dict)]
        results = [_normalize_bill(r) for r in rows]
        results = [b for b in results if b["status"] in IMMINENT_VOTE_STATUSES]
        # Newest status first so the alerts pipeline sees recent activity first.
        results.sort(key=lambda b: b.get("status_date", ""), reverse=True)
        ai_cache.set(cache_key, results, ttl_hours=_BILLS_TTL_HOURS)
        print(f"[legiscan] {state}: {len(results)} active bills (engrossed) from session {session_id}")
        return results
    except Exception as e:
        print(f"[legiscan] active-bills fetch for {state} failed ({e}), using sample data")
        return _sample_active_bills(state)


def _sample_active_bills(state: str) -> list[dict]:
    """Sample active bills with status_date set to today so V (vote-proximity) is high."""
    from datetime import date as _date
    today = _date.today().isoformat()
    out = []
    for b in SAMPLE_ACTIVE_BILLS.get(state, []):
        clone = dict(b)
        if not clone.get("status_date"):
            clone["status_date"] = today
        out.append(clone)
    # Mirror the live filter so sample/live behave identically.
    return [b for b in out if b.get("status") in IMMINENT_VOTE_STATUSES]
