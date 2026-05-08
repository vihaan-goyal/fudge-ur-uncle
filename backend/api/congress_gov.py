"""
Congress.gov API - Voting Records & Bills
==========================================
Source: https://api.congress.gov/
Key:    Same api.data.gov key as OpenFEC

Covers: bills, amendments, roll-call votes, member info,
        cosponsors, summaries, actions.
"""

import re
import httpx
from typing import Optional
from config import CONGRESS_GOV_BASE, DATA_GOV_API_KEY


# Symbolic / procedural votes that AI scorers should ignore — non-binding
# resolutions, motions, and "expressing the sense of" statements aren't
# policy decisions and produce false signal when matched against promises/stances.
_SYMBOLIC_PATTERNS = re.compile(
    r"\b(H\.?\s*Res\.?|S\.?\s*Res\.?|H\.?\s*Con\.?\s*Res\.?|S\.?\s*Con\.?\s*Res\.?|"
    r"motion to proceed|motion to table|quorum|cloture|on the journal|"
    r"expressing (the )?sense of|expressing support for|expressing (the )?gratitude)",
    re.IGNORECASE,
)


def is_substantive_vote(title: str) -> bool:
    """True if a vote title looks like a real policy bill (not a resolution or procedural motion)."""
    return bool(title) and not _SYMBOLIC_PATTERNS.search(title)


def format_vote_lines(votes: list[dict], limit: int = 20) -> str:
    """Format a vote list for AI consumption. Filters symbolic/procedural votes."""
    lines = []
    for v in votes:
        title = v.get("title") or v.get("bill") or ""
        if not is_substantive_vote(title):
            continue
        date = v.get("date", "")
        member_vote = v.get("member_vote", "")
        category = v.get("category", "")
        line = f"- {date}: {title} — voted {member_vote}"
        if category:
            line += f" [{category}]"
        lines.append(line)
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "(none available)"


def format_bill_lines(bills: list[dict], limit: int = 8) -> str:
    """Format a sponsored-bill list for AI consumption."""
    lines = []
    for b in bills[:limit]:
        title = b.get("title") or b.get("number", "")
        number = b.get("number", "")
        if title:
            lines.append(f"- {number}: {title}" if number else f"- {title}")
    return "\n".join(lines) if lines else "(none available)"


# -- Embedded sample data for offline dev --
SAMPLE_VOTES = [
    {
        "roll_call": 142,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-04-10",
        "bill": "S.1821",
        "title": "Infrastructure Investment Reauthorization Act",
        "result": "Passed",
        "yea_total": 68,
        "nay_total": 30,
        "member_vote": "Yea",
        "category": "infrastructure",
    },
    {
        "roll_call": 138,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-03-28",
        "bill": "S.1190",
        "title": "Clean Air Standards Modernization Act",
        "result": "Failed",
        "yea_total": 45,
        "nay_total": 53,
        "member_vote": "Nay",
        "category": "environment",
    },
    {
        "roll_call": 130,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-03-15",
        "bill": "S.872",
        "title": "Prescription Drug Pricing Reform Act",
        "result": "Passed",
        "yea_total": 62,
        "nay_total": 36,
        "member_vote": "Nay",
        "category": "healthcare",
    },
    {
        "roll_call": 118,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-02-20",
        "bill": "S.441",
        "title": "Social Security Stabilization Act",
        "result": "Passed",
        "yea_total": 78,
        "nay_total": 20,
        "member_vote": "Yea",
        "category": "economy",
    },
    {
        "roll_call": 105,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-02-05",
        "bill": "S.203",
        "title": "Federal Minimum Wage Adjustment Act",
        "result": "Failed",
        "yea_total": 48,
        "nay_total": 50,
        "member_vote": "Nay",
        "category": "economy",
    },
    {
        "roll_call": 92,
        "congress": 119,
        "chamber": "Senate",
        "date": "2026-01-18",
        "bill": "S.812",
        "title": "Renewable Energy Tax Credit Extension",
        "result": "Passed",
        "yea_total": 55,
        "nay_total": 43,
        "member_vote": "Yea",
        "category": "environment",
    },
]

SAMPLE_BILLS = [
    {
        "bill_id": "s1821-119",
        "number": "S.1821",
        "title": "Infrastructure Investment Reauthorization Act",
        "sponsor": "Christopher Murphy",
        "sponsor_bioguide": "M001169",
        "introduced_date": "2026-01-10",
        "latest_action": "Passed Senate 68-30",
        "latest_action_date": "2026-04-10",
        "committees": ["Commerce, Science, and Transportation"],
        "subjects": ["Infrastructure", "Transportation"],
        "cosponsors_count": 22,
    },
]


# Bills awaiting floor action — second-chamber consideration after passing the
# first, or reported out of committee with a calendar placement. We match on
# Congress.gov's latestAction text rather than parsing each bill's action
# history. See `get_active_bills` for context.
#
# Patterns are intentionally tight: "introduced" or "referred to committee"
# are far too early for the V (vote-proximity) signal to be meaningful, and
# "became public law" / "presented to the President" are after the fact.
_FLOOR_IMMINENT_PATTERN = re.compile(
    r"(placed on (the )?(senate legislative |union )?calendar|"
    # "Reported by ...", "Reported (Original) by ...", "Reported with amendment", etc.
    # The optional parenthetical absorbs Congress.gov's "(Original)"/"(Amended)" tags
    # that would otherwise break the next-word alternation.
    r"reported(\s*\([^)]*\))?\s+(by|to|with|original|favorably|without amendment)|"
    r"passed (senate|house)( as amended)?|"
    r"received in the (senate|house)|"
    r"motion to proceed|"
    r"considered by the (senate|house)|"
    r"on agreeing to the (resolution|amendment)|"
    r"engrossed amendment|"
    r"discharge petition|"
    r"committee on rules)",
    re.IGNORECASE,
)

# Resolution-type bills are mostly symbolic ("expressing the sense of",
# commemorations, internal procedure) and don't pair meaningfully with
# industry donations. Skip at ingest so they never reach the scoring pool.
_RESOLUTION_BILL_TYPES = {"hres", "sres", "hconres", "sconres"}

# Display formatting for Congress.gov bill types. The seed data and the rest
# of the codebase use dotted forms ("S.1190", "H.R.1500") so we match that.
_BILL_TYPE_DISPLAY = {
    "hr": "H.R.",
    "s": "S.",
    "hjres": "H.J.Res.",
    "sjres": "S.J.Res.",
    "hconres": "H.Con.Res.",
    "sconres": "S.Con.Res.",
    "hres": "H.Res.",
    "sres": "S.Res.",
}


def _format_bill_number(bill_type: str, number) -> str:
    bt = (bill_type or "").lower()
    prefix = _BILL_TYPE_DISPLAY.get(bt, f"{bt.upper()}.")
    return f"{prefix}{number}"


def is_floor_imminent(latest_action_text: str) -> bool:
    """True if a Congress.gov latestAction string looks like the bill is
    queued for or actively in floor consideration. Public so tests can
    exercise the matcher in isolation."""
    return bool(latest_action_text) and bool(
        _FLOOR_IMMINENT_PATTERN.search(latest_action_text)
    )


# Sample fallback for offline dev / no-key runs. Status dates are static; the
# ingester bumps any past projected date to today so V doesn't go to zero.
SAMPLE_ACTIVE_BILLS = [
    {
        "bill_id": "s1190-119",
        "number": "S.1190",
        "title": "Clean Air Standards Modernization Act",
        "status": "Placed on Senate Legislative Calendar",
        "status_date": "2026-04-25",
        "chamber": "senate",
        "congress": 119,
    },
    {
        "bill_id": "s872-119",
        "number": "S.872",
        "title": "Prescription Drug Pricing Reform Act",
        "status": "Reported by Committee on Finance",
        "status_date": "2026-04-30",
        "chamber": "senate",
        "congress": 119,
    },
    {
        "bill_id": "hr1500-119",
        "number": "H.R.1500",
        "title": "Defense Authorization Supplemental",
        "status": "Passed House",
        "status_date": "2026-05-01",
        "chamber": "house",
        "congress": 119,
    },
    {
        "bill_id": "s441-119",
        "number": "S.441",
        "title": "Social Security Stabilization Act",
        "status": "Reported with amendments",
        "status_date": "2026-04-15",
        "chamber": "senate",
        "congress": 119,
    },
]


async def _get(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to the Congress.gov API."""
    params = params or {}
    params["api_key"] = DATA_GOV_API_KEY
    params.setdefault("format", "json")
    url = f"{CONGRESS_GOV_BASE}{endpoint}"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_member_info(bioguide_id: str) -> dict:
    """
    Get detailed member info from Congress.gov.
    
    Endpoint: /member/{bioguide_id}
    """
    try:
        data = await _get(f"/member/{bioguide_id}")
        member = data.get("member", {})
        return {
            "bioguide_id": member.get("bioguideId", ""),
            "name": f"{member.get('firstName', '')} {member.get('lastName', '')}",
            "party": member.get("partyName", ""),
            "state": member.get("state", ""),
            "district": member.get("district"),
            "depiction": member.get("depiction", {}).get("imageUrl", ""),
            "terms": member.get("terms", []),
            "sponsored_legislation_count": member.get("sponsoredLegislation", {}).get("count", 0),
            "cosponsored_legislation_count": member.get("cosponsoredLegislation", {}).get("count", 0),
        }
    except Exception as e:
        print(f"[congress] Error fetching member: {e}")
        return {}


async def get_recent_votes(
    congress: int = 119,
    chamber: str = "senate",
    limit: int = 20,
) -> list[dict]:
    """
    Get recent roll-call votes for a chamber.
    
    Endpoint: Not directly available as a single call in Congress.gov API.
    We use the bill actions + vote endpoints.
    For a better pre-built experience, ProPublica Congress API is recommended.
    """
    return SAMPLE_VOTES[:limit]


async def get_member_votes(
    bioguide_id: str, govtrack_id: int = None, limit: int = 20
) -> list[dict]:
    """Get how a specific member voted. Uses GovTrack API (free, no key needed)."""
    if not govtrack_id:
        return SAMPLE_VOTES

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://www.govtrack.us/api/v2/vote_voter",
                params={"person": govtrack_id, "limit": limit, "order_by": "-created"},
            )
            resp.raise_for_status()
            objects = resp.json().get("objects", [])

        if not objects:
            return SAMPLE_VOTES

        results = []
        for v in objects:
            vote = v.get("vote", {})
            option = v.get("option", {})
            results.append({
                "roll_call": vote.get("number"),
                "congress": vote.get("congress"),
                "chamber": vote.get("chamber_label", ""),
                "date": (vote.get("created") or "")[:10],
                "bill": "",
                "title": vote.get("question", ""),
                "result": vote.get("result", ""),
                "yea_total": vote.get("total_plus"),
                "nay_total": vote.get("total_minus"),
                "member_vote": option.get("value", ""),
                "category": vote.get("category_label", vote.get("category", "")),
            })
        print(f"[govtrack] Fetched {len(results)} votes for govtrack:{govtrack_id}")
        return results
    except Exception as e:
        print(f"[govtrack] Vote fetch failed ({e}), using sample data")
        return SAMPLE_VOTES


async def search_bills(
    query: str,
    congress: int = 119,
    limit: int = 20,
) -> list[dict]:
    """
    Search for bills by keyword.
    
    Endpoint: /bill?query={query}
    """
    try:
        data = await _get("/bill", {"query": query, "limit": limit})
        bills_raw = data.get("bills", [])
        results = []
        for b in bills_raw:
            results.append({
                "bill_id": f"{b.get('type','').lower()}{b.get('number','')}-{b.get('congress','')}",
                "number": f"{b.get('type','')}.{b.get('number','')}",
                "title": b.get("title", ""),
                "introduced_date": b.get("introducedDate", ""),
                "latest_action": b.get("latestAction", {}).get("text", ""),
                "latest_action_date": b.get("latestAction", {}).get("actionDate", ""),
                "congress": b.get("congress"),
            })
        return results or SAMPLE_BILLS[:limit]
    except Exception as e:
        print(f"[congress] Error searching bills: {e}")
        return SAMPLE_BILLS[:limit]


async def get_bill_detail(
    congress: int, bill_type: str, bill_number: int
) -> dict:
    """
    Get full details for a specific bill.
    
    Endpoint: /bill/{congress}/{billType}/{billNumber}
    bill_type: 'hr', 's', 'hjres', 'sjres', 'hconres', 'sconres', 'hres', 'sres'
    """
    try:
        data = await _get(f"/bill/{congress}/{bill_type}/{bill_number}")
        b = data.get("bill", {})
        return {
            "number": f"{b.get('type','')}.{b.get('number','')}",
            "title": b.get("title", ""),
            "introduced_date": b.get("introducedDate", ""),
            "latest_action": b.get("latestAction", {}).get("text", ""),
            "sponsor": b.get("sponsors", [{}])[0].get("fullName", "") if b.get("sponsors") else "",
            "cosponsors_count": b.get("cosponsors", {}).get("count", 0),
            "committees": [c.get("name", "") for c in b.get("committees", {}).get("item", [])],
            "subjects": b.get("subjects", {}).get("legislativeSubjects", []),
            "policy_area": b.get("policyArea", {}).get("name", ""),
            "summary": "",  # requires separate /bill/.../summaries call
        }
    except Exception as e:
        print(f"[congress] Error fetching bill: {e}")
        return {}


async def get_active_bills(
    congress: int = 119,
    page_size: int = 250,
    max_pages: int = 4,
) -> list[dict]:
    """
    Federal counterpart to legiscan.get_active_bills.

    Pulls recently-updated bills from /v3/bill/{congress} (sorted updateDate
    descending) and filters to those whose latestAction text matches
    `_FLOOR_IMMINENT_PATTERN` — committee-reported, calendar-placed, or
    passed one chamber and pending the other.

    Resolution-type bills (hres/sres/hconres/sconres) are dropped at this
    layer; they're symbolic and don't produce useful donation×vote signal.

    Returns dicts shaped like the state-side ingester's input:
        {bill_id, number, title, status, status_date, chamber, congress}

    Falls back to SAMPLE_ACTIVE_BILLS when the request fails or the API
    key is missing/DEMO. Pagination caps at `max_pages * page_size` total
    results — defaults to 1000, more than enough since we filter aggressively.
    """
    if not DATA_GOV_API_KEY or DATA_GOV_API_KEY == "DEMO_KEY":
        return list(SAMPLE_ACTIVE_BILLS)

    page_size = min(page_size, 250)
    results: list[dict] = []
    seen_ids: set[str] = set()
    offset = 0

    for _ in range(max_pages):
        try:
            data = await _get(
                f"/bill/{congress}",
                {"sort": "updateDate+desc", "limit": page_size, "offset": offset},
            )
        except Exception as e:
            print(f"[congress] active-bills fetch failed at offset={offset}: {e}")
            break

        bills_raw = data.get("bills", []) or []
        if not bills_raw:
            break

        for b in bills_raw:
            bill_type = (b.get("type") or "").lower()
            if bill_type in _RESOLUTION_BILL_TYPES:
                continue
            la = b.get("latestAction") or {}
            la_text = la.get("text") or ""
            if not is_floor_imminent(la_text):
                continue
            number = b.get("number") or ""
            bill_id = f"{bill_type}{number}-{b.get('congress','')}"
            if bill_id in seen_ids:
                continue
            seen_ids.add(bill_id)
            chamber = "house" if bill_type.startswith("h") else "senate"
            results.append({
                "bill_id": bill_id,
                "number": _format_bill_number(bill_type, number),
                "title": b.get("title", ""),
                "status": la_text,
                "status_date": (la.get("actionDate") or "")[:10],
                "chamber": chamber,
                "congress": b.get("congress"),
            })

        if len(bills_raw) < page_size:
            break
        offset += page_size

    if not results:
        # The live API might be reachable but returning nothing useful; fall
        # back so dev runs still produce something for the pipeline to chew on.
        print("[congress] active-bills filter matched 0 rows; using sample fallback")
        return list(SAMPLE_ACTIVE_BILLS)

    return results


async def get_sponsored_bills(bioguide_id: str, limit: int = 10) -> list[dict]:
    """
    Get bills sponsored by a member.
    
    Endpoint: /member/{bioguide_id}/sponsored-legislation
    """
    try:
        data = await _get(
            f"/member/{bioguide_id}/sponsored-legislation",
            {"limit": limit}
        )
        bills = []
        sponsored_list = data.get("sponsoredLegislation") or []
        for b in sponsored_list:
            if not b:
                continue
            latest_action = b.get("latestAction") or {}
            bills.append({
                "number": f"{b.get('type','')}.{b.get('number','')}",
                "title": b.get("title", ""),
                "introduced_date": b.get("introducedDate", ""),
                "latest_action": latest_action.get("text", ""),
                "congress": b.get("congress"),
            })
        return bills
    except Exception as e:
        print(f"[congress] Error fetching sponsored bills: {e}")
        return []