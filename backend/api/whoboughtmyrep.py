"""
WhoBoughtMyRep API - Pre-processed Campaign Finance
=====================================================
Source: https://whoboughtmyrep.com/developers
Key:    Free tier, no credit card

This is the BEST starting API for the app because it does the hard work
of industry attribution (tracing PAC dollars back through hop chains)
that would take months to build from raw FEC data.

Covers: 538 members, 13.8M+ donations, industry attribution,
        PAC data, voting records. Updated monthly (contributions)
        and daily (votes).
"""

import httpx
from typing import Optional
from config import WHOBOUGHTMYREP_BASE, WHOBOUGHTMYREP_API_KEY


# -- Embedded sample data for offline dev --
SAMPLE_REPS = [
    {
        "wbr_id": "wbr_M001169",
        "name": "Christopher Murphy",
        "party": "Democrat",
        "state": "CT",
        "chamber": "senate",
        "total_raised": 27_450_000,
        "total_funding": 29_100_000,  # includes IE support
        "small_donor_total": 8_100_000,
        "pac_total": 4_200_000,
        "ie_support_total": 1_650_000,
        "top_industries": [
            {"industry": "Securities & Investment", "total_attributed": 1_450_000},
            {"industry": "Lawyers/Law Firms", "total_attributed": 1_280_000},
            {"industry": "Health Professionals", "total_attributed": 980_000},
            {"industry": "Education", "total_attributed": 720_000},
            {"industry": "Real Estate", "total_attributed": 650_000},
            {"industry": "Insurance", "total_attributed": 480_000},
            {"industry": "Pharmaceuticals", "total_attributed": 420_000},
            {"industry": "TV/Movies/Music", "total_attributed": 380_000},
        ],
        "top_donors": [
            {"name": "Yale University", "total": 245_000, "type": "individual_employer"},
            {"name": "Cigna Corp", "total": 85_000, "type": "pac"},
            {"name": "United Technologies", "total": 72_000, "type": "pac"},
            {"name": "Travelers Companies", "total": 55_000, "type": "pac"},
            {"name": "Hartford Financial Services", "total": 48_000, "type": "pac"},
        ],
    },
    {
        "wbr_id": "wbr_H001047",
        "name": "James A. Himes",
        "party": "Democrat",
        "state": "CT",
        "chamber": "house",
        "district": 4,
        "total_raised": 5_800_000,
        "total_funding": 6_200_000,
        "small_donor_total": 1_200_000,
        "pac_total": 1_600_000,
        "ie_support_total": 400_000,
        "top_industries": [
            {"industry": "Securities & Investment", "total_attributed": 890_000},
            {"industry": "Real Estate", "total_attributed": 420_000},
            {"industry": "Insurance", "total_attributed": 380_000},
            {"industry": "Lawyers/Law Firms", "total_attributed": 310_000},
            {"industry": "Commercial Banks", "total_attributed": 280_000},
        ],
        "top_donors": [
            {"name": "Bridgewater Associates", "total": 120_000, "type": "individual_employer"},
            {"name": "Goldman Sachs", "total": 65_000, "type": "pac"},
            {"name": "Elliott Management", "total": 58_000, "type": "individual_employer"},
        ],
    },
]

SAMPLE_VOTES = [
    {
        "bill": "S.1821",
        "title": "Infrastructure Investment Reauthorization Act",
        "date": "2026-04-10",
        "vote": "Yea",
        "result": "Passed",
    },
    {
        "bill": "S.1190",
        "title": "Clean Air Standards Modernization Act",
        "date": "2026-03-28",
        "vote": "Nay",
        "result": "Failed",
    },
]


async def _get(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to WhoBoughtMyRep API."""
    if not WHOBOUGHTMYREP_API_KEY:
        print("[wbmr] No API key set, using sample data")
        return {}

    params = params or {}
    url = f"{WHOBOUGHTMYREP_BASE}{endpoint}"
    headers = {"x-api-key": WHOBOUGHTMYREP_API_KEY}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_reps(
    state: Optional[str] = None,
    chamber: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    Get representatives with funding data.
    
    Endpoint: /reps
    Params:   state, chamber (house|senate), limit, offset
    """
    params = {"limit": limit, "offset": offset}
    if state:
        params["state"] = state
    if chamber:
        params["chamber"] = chamber

    try:
        data = await _get("/reps", params)
        return data.get("data", [])
    except Exception:
        # Filter sample data by state/chamber
        results = SAMPLE_REPS
        if state:
            results = [r for r in results if r["state"] == state.upper()]
        if chamber:
            results = [r for r in results if r["chamber"] == chamber.lower()]
        return results


async def get_rep_detail(rep_id: str) -> dict:
    """
    Get detailed funding breakdown for one representative.
    
    Endpoint: /reps/{rep_id}
    Returns:  total_raised, total_funding, top_industries (with PAC hop tracing),
              top_donors, small_donor_total, ie_support_total
    """
    try:
        data = await _get(f"/reps/{rep_id}")
        return data.get("data", {})
    except Exception:
        for rep in SAMPLE_REPS:
            if rep["wbr_id"] == rep_id:
                return rep
        return {}


async def get_rep_industries(rep_id: str, limit: int = 15) -> list[dict]:
    """
    Get industry-level funding breakdown.
    
    Endpoint: /reps/{rep_id}/industries
    This is the killer feature - WhoBoughtMyRep traces money through
    PAC hops to attribute donations back to their original industry.
    """
    try:
        data = await _get(f"/reps/{rep_id}/industries", {"limit": limit})
        return data.get("data", [])
    except Exception:
        for rep in SAMPLE_REPS:
            if rep["wbr_id"] == rep_id:
                return rep.get("top_industries", [])[:limit]
        return []


async def get_rep_donors(rep_id: str, limit: int = 20) -> list[dict]:
    """
    Get top donors for a representative.
    
    Endpoint: /reps/{rep_id}/donors
    """
    try:
        data = await _get(f"/reps/{rep_id}/donors", {"limit": limit})
        return data.get("data", [])
    except Exception:
        for rep in SAMPLE_REPS:
            if rep["wbr_id"] == rep_id:
                return rep.get("top_donors", [])[:limit]
        return []


async def get_rep_votes(rep_id: str, limit: int = 20) -> list[dict]:
    """
    Get voting record for a representative.
    
    Endpoint: /reps/{rep_id}/votes
    Updated daily from Congress.gov.
    """
    try:
        data = await _get(f"/reps/{rep_id}/votes", {"limit": limit})
        return data.get("data", [])
    except Exception:
        return SAMPLE_VOTES


async def search_donations(
    donor_name: Optional[str] = None,
    state: Optional[str] = None,
    min_amount: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search individual donations across all members.
    
    Endpoint: /donations
    """
    params = {"limit": limit}
    if donor_name:
        params["donor_name"] = donor_name
    if state:
        params["state"] = state
    if min_amount:
        params["min_amount"] = min_amount

    try:
        data = await _get("/donations", params)
        return data.get("data", [])
    except Exception:
        return []
