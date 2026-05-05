"""
OpenFEC API - Campaign Finance Data
=====================================
Source: https://api.open.fec.gov/developers/
Key:    Free via https://api.data.gov/signup/  (DEMO_KEY works with 1K req/hr limit)

Covers: candidate totals, committee donations, PAC contributions,
        individual contributions, independent expenditures.
"""

from datetime import date
import httpx
from typing import Optional
from config import OPENFEC_BASE, DATA_GOV_API_KEY


def _current_cycle() -> int:
    """FEC cycles use the EVEN year of each 2-year period (e.g. 2026 covers 2025-2026)."""
    y = date.today().year
    return y if y % 2 == 0 else y + 1

# -- Embedded sample data for offline dev --
SAMPLE_CANDIDATE_TOTALS = {
    "S8CT00177": {
        "candidate_id": "S8CT00177",
        "candidate_name": "MURPHY, CHRISTOPHER S",
        "party": "DEM",
        "state": "CT",
        "office": "S",
        "total_receipts": 27_450_000,
        "total_disbursements": 25_100_000,
        "cash_on_hand": 3_200_000,
        "total_individual_contributions": 18_900_000,
        "total_pac_contributions": 4_200_000,
        "total_small_individual": 8_100_000,
        "cycle": 2024,
    },
    "H8CT04179": {
        "candidate_id": "H8CT04179",
        "candidate_name": "HIMES, JAMES A",
        "party": "DEM",
        "state": "CT",
        "office": "H",
        "total_receipts": 5_800_000,
        "total_disbursements": 5_200_000,
        "cash_on_hand": 1_100_000,
        "total_individual_contributions": 3_400_000,
        "total_pac_contributions": 1_600_000,
        "total_small_individual": 1_200_000,
        "cycle": 2024,
    },
}

SAMPLE_TOP_CONTRIBUTORS = [
    {"contributor_name": "YALE UNIVERSITY", "total": 245_000, "type": "individual"},
    {"contributor_name": "CIGNA CORP PAC", "total": 30_000, "type": "pac"},
    {"contributor_name": "UNITED TECHNOLOGIES", "total": 28_000, "type": "pac"},
    {"contributor_name": "COMCAST CORP PAC", "total": 25_000, "type": "pac"},
    {"contributor_name": "TRAVELERS COMPANIES", "total": 22_000, "type": "pac"},
]


async def _get(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to the OpenFEC API."""
    params = params or {}
    params["api_key"] = DATA_GOV_API_KEY
    url = f"{OPENFEC_BASE}{endpoint}"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_candidate_totals(
    candidate_id: str, cycle: Optional[int] = None
) -> dict:
    """
    Get financial summary for a candidate.

    Endpoint: /candidate/{candidate_id}/totals/
    Returns:  receipts, disbursements, cash on hand, PAC vs individual split
    """
    if cycle is None:
        cycle = _current_cycle()
    try:
        data = await _get(
            f"/candidate/{candidate_id}/totals/",
            {"cycle": cycle, "per_page": 1},
        )
        results = data.get("results", [])
        if not results:
            return {}

        r = results[0]
        return {
            "candidate_id": candidate_id,
            "candidate_name": r.get("candidate_name", ""),
            "party": r.get("party", ""),
            "state": r.get("state", ""),
            "office": r.get("office", ""),
            "total_receipts": r.get("receipts", 0),
            "total_disbursements": r.get("disbursements", 0),
            "cash_on_hand": r.get("last_cash_on_hand_end_period", 0),
            "total_individual_contributions": r.get("individual_contributions", 0),
            "total_pac_contributions": r.get("other_political_committee_contributions", 0),
            "total_small_individual": r.get("individual_unitemized_contributions", 0),
            "cycle": cycle,
        }
    except Exception as e:
        print(f"[openfec] Error fetching candidate totals: {e}")
        return SAMPLE_CANDIDATE_TOTALS.get(candidate_id, {})


async def _get_principal_committee_id(candidate_id: str, cycle: int) -> str:
    """Resolve a candidate_id to their principal committee_id."""
    cand_data = await _get(f"/candidate/{candidate_id}/", {"cycle": cycle})
    results = cand_data.get("results", [])
    if not results:
        return ""
    return results[0].get("principal_committees", [{}])[0].get("committee_id", "")


async def get_top_contributors(
    candidate_id: str, cycle: Optional[int] = None, limit: int = 10
) -> list[dict]:
    """Get top contributing committees/PACs. Endpoint: /schedules/schedule_a/by_contributor/"""
    if cycle is None:
        cycle = _current_cycle()
    try:
        committee_id = await _get_principal_committee_id(candidate_id, cycle)
        if not committee_id:
            return SAMPLE_TOP_CONTRIBUTORS[:limit]

        data = await _get(
            "/schedules/schedule_a/by_contributor/",
            {"committee_id": committee_id, "cycle": cycle, "sort": "-total", "per_page": limit},
        )
        contributors = [
            {
                "contributor_name": r.get("contributor_name", ""),
                "total": r.get("total", 0),
                "type": "pac" if "PAC" in r.get("contributor_name", "").upper() else "individual",
            }
            for r in data.get("results", [])
        ]
        return contributors or SAMPLE_TOP_CONTRIBUTORS[:limit]
    except Exception as e:
        print(f"[openfec] Error fetching contributors: {e}")
        return SAMPLE_TOP_CONTRIBUTORS[:limit]


async def get_top_employers(
    candidate_id: str, cycle: Optional[int] = None, limit: int = 10
) -> list[dict]:
    """
    Get top employers of individual donors — the same methodology OpenSecrets uses.
    Aggregates itemized individual contributions by the donor's listed employer.
    Endpoint: /schedules/schedule_a/by_employer/
    """
    if cycle is None:
        cycle = _current_cycle()
    try:
        committee_id = await _get_principal_committee_id(candidate_id, cycle)
        if not committee_id:
            return []

        data = await _get(
            "/schedules/schedule_a/by_employer/",
            {"committee_id": committee_id, "cycle": cycle, "sort": "-total", "per_page": limit},
        )
        results = []
        for r in data.get("results", []):
            employer = (r.get("employer") or "").strip()
            if not employer or employer.upper() in ("RETIRED", "SELF-EMPLOYED", "N/A", "NONE", "NOT EMPLOYED"):
                continue
            results.append({
                "name": employer.title(),
                "total": r.get("total", 0),
                "count": r.get("count", 0),
                "type": "individual",
            })
        print(f"[openfec] Got {len(results)} top employers for {candidate_id}")
        return results[:limit]
    except Exception as e:
        print(f"[openfec] Error fetching top employers: {e}")
        return []


async def get_independent_expenditures(
    candidate_id: str, cycle: Optional[int] = None, limit: int = 20
) -> list[dict]:
    """
    Get independent expenditures for/against a candidate.

    Endpoint: /schedules/schedule_e/by_candidate/
    These are PAC ads, mailers, etc. that are NOT coordinated with the campaign.
    """
    if cycle is None:
        cycle = _current_cycle()
    try:
        data = await _get(
            "/schedules/schedule_e/by_candidate/",
            {
                "candidate_id": candidate_id,
                "cycle": cycle,
                "per_page": limit,
            },
        )
        results = []
        for r in data.get("results", []):
            results.append({
                "committee_name": r.get("committee_name", ""),
                "total": r.get("total", 0),
                "support_oppose": r.get("support_oppose_indicator", ""),
            })
        return results
    except Exception as e:
        print(f"[openfec] Error fetching IEs: {e}")
        return []


async def search_candidates(
    name: Optional[str] = None,
    state: Optional[str] = None,
    office: Optional[str] = None,
    cycle: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search for candidates by name, state, or office.

    office: 'H' (House), 'S' (Senate), 'P' (President)
    """
    if cycle is None:
        cycle = _current_cycle()
    params = {"cycle": cycle, "per_page": limit, "sort": "-receipts"}
    if name:
        params["q"] = name
    if state:
        params["state"] = state
    if office:
        params["office"] = office

    try:
        data = await _get("/candidates/search/", params)
        results = []
        for r in data.get("results", []):
            results.append({
                "candidate_id": r.get("candidate_id", ""),
                "name": r.get("name", ""),
                "party": r.get("party", ""),
                "state": r.get("state", ""),
                "office": r.get("office", ""),
                "district": r.get("district", ""),
                "cycles": r.get("cycles", []),
            })
        return results
    except Exception as e:
        print(f"[openfec] Error searching candidates: {e}")
        return []
