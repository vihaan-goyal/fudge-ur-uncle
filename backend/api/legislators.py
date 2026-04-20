"""
Legislators data from unitedstates/congress-legislators GitHub repo.
Free, no API key needed. Contains all current federal legislators
with contact info, social media, IDs for cross-referencing other APIs.
"""

import json
import httpx
from typing import Optional
from config import LEGISLATORS_GITHUB_URL

_cache: list[dict] = []


# -- Embedded sample for offline dev / demo --
SAMPLE_LEGISLATORS = [
    {
        "id": {"bioguide": "B000575", "fec": ["S6MO00093"], "govtrack": 400034},
        "name": {"first": "Roy", "last": "Blunt", "official_full": "Roy Blunt"},
        "bio": {"gender": "M", "birthday": "1950-01-10"},
        "terms": [
            {
                "type": "sen", "start": "2023-01-03", "end": "2029-01-03",
                "state": "MO", "party": "Republican",
                "phone": "202-224-5721",
                "url": "https://www.blunt.senate.gov",
                "contact_form": "https://www.blunt.senate.gov/contact/contact-roy",
                "office": "260 Russell Senate Office Building",
            }
        ],
    },
    {
        "id": {"bioguide": "M001169", "fec": ["S8CT00177"], "govtrack": 412194},
        "name": {"first": "Chris", "last": "Murphy", "official_full": "Christopher Murphy"},
        "bio": {"gender": "M", "birthday": "1973-08-03"},
        "terms": [
            {
                "type": "sen", "start": "2025-01-03", "end": "2031-01-03",
                "state": "CT", "party": "Democrat",
                "phone": "202-224-4041",
                "url": "https://www.murphy.senate.gov",
                "office": "136 Hart Senate Office Building",
            }
        ],
    },
    {
        "id": {"bioguide": "B001277", "fec": ["S0CT00177"], "govtrack": 412490},
        "name": {"first": "Richard", "last": "Blumenthal", "official_full": "Richard Blumenthal"},
        "bio": {"gender": "M", "birthday": "1946-02-13"},
        "terms": [
            {
                "type": "sen", "start": "2023-01-03", "end": "2029-01-03",
                "state": "CT", "party": "Democrat",
                "phone": "202-224-2823",
                "url": "https://www.blumenthal.senate.gov",
                "office": "706 Hart Senate Office Building",
            }
        ],
    },
    {
        "id": {"bioguide": "H001047", "fec": ["H8CT04179"], "govtrack": 412282},
        "name": {"first": "Jim", "last": "Himes", "official_full": "James A. Himes"},
        "bio": {"gender": "M", "birthday": "1966-07-05"},
        "terms": [
            {
                "type": "rep", "start": "2025-01-03", "end": "2027-01-03",
                "state": "CT", "district": 4, "party": "Democrat",
                "phone": "202-225-5541",
                "url": "https://himes.house.gov",
                "office": "1227 Longworth House Office Building",
            }
        ],
    },
]


async def fetch_legislators(use_cache: bool = True) -> list[dict]:
    """Fetch all current legislators. Falls back to sample data if GitHub is unavailable."""
    global _cache
    if use_cache and _cache:
        return _cache

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(LEGISLATORS_GITHUB_URL)
            resp.raise_for_status()
            _cache = resp.json()
            print(f"[legislators] Fetched {len(_cache)} from GitHub")
            return _cache
    except Exception as e:
        print(f"[legislators] GitHub unavailable ({e}), using sample data")
        _cache = SAMPLE_LEGISLATORS
        return _cache


def _current_term(legislator: dict) -> dict:
    """Get the most recent term for a legislator."""
    return legislator.get("terms", [{}])[-1]


def normalize(legislator: dict) -> dict:
    """Normalize raw legislator data into the shape our frontend expects."""
    term = _current_term(legislator)
    ids = legislator.get("id", {})
    name = legislator.get("name", {})

    chamber = "Senate" if term.get("type") == "sen" else "House"
    district = term.get("state", "")
    if term.get("type") == "rep":
        district = f"{term.get('state', '')}-{term.get('district', '?')}"

    party_full = term.get("party", "")
    party_letter = party_full[0] if party_full else "?"

    return {
        "bioguide_id": ids.get("bioguide", ""),
        "fec_ids": ids.get("fec", []),
        "govtrack_id": ids.get("govtrack"),
        "name": name.get("official_full", f"{name.get('first','')} {name.get('last','')}"),
        "first_name": name.get("first", ""),
        "last_name": name.get("last", ""),
        "party": party_letter,
        "party_full": party_full,
        "state": term.get("state", ""),
        "district": district,
        "chamber": chamber,
        "phone": term.get("phone", ""),
        "website": term.get("url", ""),
        "office": term.get("office", ""),
        "contact_form": term.get("contact_form", ""),
        "term_start": term.get("start", ""),
        "term_end": term.get("end", ""),
    }


async def search_by_state(state: str) -> list[dict]:
    """Get all federal legislators for a state (e.g., 'CT')."""
    all_legs = await fetch_legislators()
    results = []
    for leg in all_legs:
        term = _current_term(leg)
        if term.get("state", "").upper() == state.upper():
            results.append(normalize(leg))
    return results


async def search_by_name(query: str) -> list[dict]:
    """Search legislators by name."""
    all_legs = await fetch_legislators()
    q = query.lower()
    results = []
    for leg in all_legs:
        name = leg.get("name", {})
        full = name.get("official_full", "").lower()
        if q in full or q in name.get("last", "").lower():
            results.append(normalize(leg))
    return results


async def get_by_bioguide(bioguide_id: str) -> Optional[dict]:
    """Get a single legislator by their Bioguide ID."""
    all_legs = await fetch_legislators()
    for leg in all_legs:
        if leg.get("id", {}).get("bioguide") == bioguide_id:
            return normalize(leg)
    return None
