"""
WhoBoughtMyRep API - Pre-processed Campaign Finance
=====================================================
Source: https://whoboughtmyrep.com/developers
Key:    Free tier = 100 requests/day

Free tier endpoints:
  GET /reps                 - list & search members
  GET /reps/{bioguide_id}   - full profile (includes top_industries)
  GET /reps/{id}/committees - committee memberships
  GET /industries           - industry overview

Pro-only ($49/mo):
  /reps/{id}/donors, /reps/{id}/votes, /donors/search, etc.

Names are in FEC format: "Last, First M."
"""

import time
import httpx
from typing import Optional
from config import WHOBOUGHTMYREP_BASE, WHOBOUGHTMYREP_API_KEY


# -- In-memory cache to stay within 100/day limit --
# WBMR uses full state names (e.g. "Connecticut"), not 2-letter codes
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "AS": "American Samoa", "GU": "Guam", "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico", "VI": "Virgin Islands",
}
_cache: dict = {}
CACHE_TTL = 3600  # 1 hour; WBMR data updates monthly


# -- Sample fallback matching real API shape --
SAMPLE_REPS = [
    {
        "bioguide_id": "M001169",
        "name": "Murphy, Christopher S.",
        "party": "Democratic",
        "state": "CT",
        "chamber": "senate",
        "total_raised": 27450000,
        "total_funding": 29100000,
        "pac_percent": 15.3,
        "small_donor_percent": 27.8,
        "ie_support_total": 1650000,
    },
]


async def _get(endpoint: str, params: dict = None, use_cache: bool = True) -> Optional[dict]:
    """Authenticated request. Returns parsed JSON or None on failure."""
    if not WHOBOUGHTMYREP_API_KEY:
        print("[wbmr] No API key set, using sample data")
        return None

    cache_key = f"{endpoint}?{params}"
    if use_cache and cache_key in _cache:
        ts, data = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return data

    url = f"{WHOBOUGHTMYREP_BASE}{endpoint}"
    headers = {"x-api-key": WHOBOUGHTMYREP_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, params=params or {}, headers=headers)
            if resp.status_code == 401:
                print("[wbmr] Invalid API key (401)")
                return None
            if resp.status_code == 403:
                print(f"[wbmr] Endpoint requires Pro tier: {endpoint}")
                return None
            if resp.status_code == 429:
                print("[wbmr] Rate limit hit (100/day on free tier)")
                return None
            resp.raise_for_status()
            data = resp.json()

            if use_cache:
                _cache[cache_key] = (time.time(), data)

            return data
    except Exception as e:
        print(f"[wbmr] Request failed: {e}")
        return None

async def get_reps(
    state: Optional[str] = None,
    chamber: Optional[str] = None,
    party: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """List & search members. GET /reps"""
    params = {"limit": limit, "offset": offset}
    if state:
        # WBMR wants full state names like "Connecticut", not "CT"
        state_upper = state.upper()
        params["state"] = STATE_NAMES.get(state_upper, state)
    if chamber:
        params["chamber"] = chamber
    if party:
        params["party"] = party
    if query:
        params["q"] = query

    response = await _get("/reps", params)
    if response is None:
        results = SAMPLE_REPS
        if state:
            results = [r for r in results if r["state"] == state.upper()]
        return results
    return response.get("data", [])

async def get_rep_by_bioguide(bioguide_id: str) -> Optional[dict]:
    """Full profile with top_industries. GET /reps/{bioguide_id}"""
    response = await _get(f"/reps/{bioguide_id}")
    if response is None:
        return None
    return response.get("data")


async def get_rep_committees(bioguide_id: str) -> list[dict]:
    """Committee memberships. GET /reps/{bioguide_id}/committees"""
    response = await _get(f"/reps/{bioguide_id}/committees")
    if response is None:
        return []
    return response.get("data", [])


async def get_industries(limit: int = 20) -> list[dict]:
    """Industry overview. GET /industries"""
    response = await _get("/industries", {"limit": limit})
    if response is None:
        return []
    return response.get("data", [])

def normalize_rep_funding(rep: dict) -> dict:
    """Shape funding data consistently for the frontend."""
    if not rep:
        return {
            "total_raised": 0,
            "total_funding": 0,
            "pac_total": 0,
            "small_donor_total": 0,
            "individual_total": 0,
            "ie_support_total": 0,
            "top_industries": [],
            "top_donors": [],
            "grassroots_rank": None,
        }

    return {
        "total_raised": rep.get("total_raised") or 0,
        "total_funding": rep.get("total_funding") or 0,
        "pac_total": rep.get("pac_total") or 0,
        "small_donor_total": rep.get("small_donor_total") or 0,
        "individual_total": rep.get("individual_total") or 0,
        "ie_support_total": rep.get("ie_support_total") or 0,
        "top_industries": rep.get("top_industries") or [],
        "top_donors": [],  # Pro tier only
        "grassroots_rank": rep.get("grassroots_chamber_rank"),
    }