"""
FollowTheMoney (NIMP) API wrapper - state campaign-finance aggregates.

Powers `/api/state-alerts/*`. The free tier is generous but the docs are
notoriously cryptic — every request takes a `gro` (group), `for` (filter),
and various other coded params. The endpoint constants below are the
best-known-good values; if NIMP renames anything, swap them here in one
place rather than threading through ingest_ftm.py.

Public functions:
  - find_candidate_eid(name, state, chamber, party) -> (eid, confidence) | None
  - get_industry_aggregates(eid, cycle) -> list[{catcode, amount, n_records}]

Both go through ai_cache (24h TTL) because the free tier's monthly cap is
real and aggregates barely move within a cycle.

Falls back to SAMPLE_FTM_DATA when:
  - FTM_API_KEY is not set, OR
  - upstream returns an error / unrecognized shape

This mirrors the legiscan.py / news.py / guardian.py pattern of "always
return something usable so the demo runs even without keys."
"""
import asyncio
from difflib import SequenceMatcher
from typing import Optional

import httpx

from config import FTM_API_KEY  # type: ignore
from api import ai_cache

_TIMEOUT = 20.0
_FTM_BASE = "https://api.followthemoney.org/"

# Cache TTLs in hours
_EID_TTL = 24 * 7      # eid lookups: a state legislator's FTM mapping is stable
_AGGS_TTL = 24         # industry aggregates: cycle data updates slowly

# Confidence threshold for fuzzy name matches; below this we drop the result
# rather than attribute donations to the wrong person.
_MIN_MATCH_CONFIDENCE = 0.78


# ---- Sample data for offline / no-key dev ---------------------------

# Sample state-legislator -> FTM eid mappings for demo / no-key dev.
# Stored as (state, name) -> eid; lookup is fuzzy so small name variations
# (middle initials, suffixes) still resolve.
SAMPLE_FTM_EIDS = {
    ("CT", "Martin Looney"): "FTM-CT-9001",
    ("CT", "Matt Ritter"): "FTM-CT-9002",
}

# Keyed by (eid, cycle). Returns list[{catcode, amount, n_records}].
# Industries chosen to give the demo something the alert pipeline will
# actually flag against SAMPLE_ACTIVE_BILLS in legiscan.py:
#   - HB-5485 (pharma drug pricing) <-- pharma + health-insurance donations
#   - SB-872  (climate / renewable)  <-- oil/gas + electric-utility donations
_LOONEY_AGG = [
    {"catcode": "H1410", "amount": 35_000.0, "n_records": 11},  # pharma
    {"catcode": "H1300", "amount": 18_000.0, "n_records": 6},   # health insurance
    {"catcode": "E1100", "amount": 22_000.0, "n_records": 8},   # oil & gas
    {"catcode": "F2100", "amount": 12_500.0, "n_records": 5},   # commercial banks
    {"catcode": "L1500", "amount": 45_000.0, "n_records": 22},  # public sector unions
]
_RITTER_AGG = [
    {"catcode": "E1100", "amount": 18_000.0, "n_records": 7},   # oil & gas
    {"catcode": "H1410", "amount": 22_000.0, "n_records": 9},   # pharma
    {"catcode": "F2400", "amount": 9_500.0, "n_records": 4},    # insurance
]
SAMPLE_FTM_AGGREGATES = {
    ("FTM-CT-9001", 2024): _LOONEY_AGG,
    ("FTM-CT-9001", 2026): _LOONEY_AGG,
    ("FTM-CT-9002", 2024): _RITTER_AGG,
    ("FTM-CT-9002", 2026): _RITTER_AGG,
}


# ---- Low-level HTTP -------------------------------------------------

async def _ftm_get(client: httpx.AsyncClient, params: dict) -> dict:
    """GET against FTM with the API key attached. Retries 429 with backoff."""
    if not FTM_API_KEY:
        raise RuntimeError("FTM_API_KEY not set")
    full = {**params, "APIKey": FTM_API_KEY, "mode": "json"}
    for attempt in range(3):
        try:
            resp = await client.get(_FTM_BASE, params=full, timeout=_TIMEOUT)
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            if attempt == 2:
                raise
            await asyncio.sleep(1)
    return {}


# ---- EID lookup -----------------------------------------------------

def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _lookup_sample_eid(name: str, state: str) -> Optional[tuple[str, float]]:
    """Fuzzy-match the demo SAMPLE_FTM_EIDS so middle initials/suffixes don't break it."""
    state_u = state.upper()
    best: Optional[tuple[str, float]] = None
    for (s, sample_name), eid in SAMPLE_FTM_EIDS.items():
        if s != state_u:
            continue
        conf = _name_similarity(name, sample_name)
        if best is None or conf > best[1]:
            best = (eid, conf)
    if best and best[1] >= _MIN_MATCH_CONFIDENCE:
        return best
    return None


async def _live_find_eid(
    client: httpx.AsyncClient, name: str, state: str, chamber: str, party: Optional[str]
) -> Optional[tuple[str, float]]:
    """Search FTM's candidate index for a name match. Returns (eid, confidence) or None.

    NIMP uses a candidate-search aggregation. Param names per their docs:
      gro=c-t-id   (group: candidate, table: id)
      so=ASC       (sort)
      dataset=candidates
      f-eid=...    (filter by eid — when known)
      c-r-ot=H/S   (chamber: House/Senate)
      s-y-st=CT    (state)
    Verify these against current docs before relying on a real key.
    """
    chamber_code = "H" if chamber.lower().startswith("h") else "S"
    params = {
        "gro": "c-t-id",
        "so": "ASC",
        "dataset": "candidates",
        "s-y-st": state.upper(),
        "c-r-ot": chamber_code,
        "search": name,
    }
    if party:
        params["c-t-p"] = party.upper()[:1]  # D / R / I

    data = await _ftm_get(client, params)
    records = data.get("records") or data.get("Records") or []
    if not records:
        return None

    best: Optional[tuple[str, float]] = None
    for r in records:
        candidate_name = r.get("Candidate") or r.get("name") or ""
        eid = r.get("Candidate_Entity") or r.get("eid")
        if not eid or not candidate_name:
            continue
        conf = _name_similarity(name, candidate_name)
        if best is None or conf > best[1]:
            best = (str(eid), conf)
    if best and best[1] >= _MIN_MATCH_CONFIDENCE:
        return best
    return None


async def find_candidate_eid(
    name: str, state: str, chamber: str, party: Optional[str] = None
) -> Optional[tuple[str, float]]:
    """Return (FTM eid, match confidence) for a state legislator, or None if no good match.

    Confidence is the SequenceMatcher ratio between the requested name and the
    name on the matched FTM record; below `_MIN_MATCH_CONFIDENCE` we discard
    rather than risk attributing donations to the wrong person.
    """
    cache_key = f"ftm:eid:{state.upper()}:{chamber.lower()}:{name.lower().strip()}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        # Empty list = cached "no match"; non-empty list = cached [eid, confidence].
        return tuple(cached) if cached else None  # type: ignore[return-value]

    if not FTM_API_KEY:
        sample = _lookup_sample_eid(name, state)
        ai_cache.set(cache_key, list(sample) if sample else [], ttl_hours=_EID_TTL)
        return sample

    try:
        async with httpx.AsyncClient() as client:
            result = await _live_find_eid(client, name, state, chamber, party)
    except Exception as e:
        print(f"[ftm]   eid lookup failed for {name} ({state}/{chamber}): {e!r}")
        result = None

    ai_cache.set(cache_key, list(result) if result else [], ttl_hours=_EID_TTL)
    return result


# ---- Industry aggregates --------------------------------------------

async def _live_get_aggregates(
    client: httpx.AsyncClient, eid: str, cycle: int
) -> list[dict]:
    """Pull the candidate's industry breakdown for one cycle.

    NIMP industry-breakdown aggregation:
      gro=s-x-cc       (group: by Catcode)
      dataset=candidates
      f-eid=<EID>      (filter to this candidate)
      y=<cycle>        (year/cycle)
    Returns rows like {Catcode, Total_$, Records}.
    Verify against current docs before relying on a real key.
    """
    params = {
        "gro": "s-x-cc",
        "dataset": "candidates",
        "f-eid": eid,
        "y": cycle,
    }
    data = await _ftm_get(client, params)
    records = data.get("records") or data.get("Records") or []
    out = []
    for r in records:
        catcode = r.get("Catcode") or r.get("catcode")
        total = r.get("Total_$") or r.get("total") or 0
        n = r.get("Records") or r.get("n_records") or 0
        if not catcode:
            continue
        try:
            amount = float(str(total).replace(",", "").replace("$", "")) or 0.0
        except ValueError:
            amount = 0.0
        if amount <= 0:
            continue
        out.append({
            "catcode": str(catcode).strip().upper(),
            "amount": amount,
            "n_records": int(n) if str(n).isdigit() else 0,
        })
    return out


async def get_industry_aggregates(eid: str, cycle: int) -> list[dict]:
    """Industry breakdown for one candidate-cycle. Returns list of dicts.

    Each dict: {"catcode": str, "amount": float, "n_records": int}
    """
    cache_key = f"ftm:aggs:{eid}:{cycle}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    if not FTM_API_KEY:
        result = SAMPLE_FTM_AGGREGATES.get((eid, cycle), [])
        ai_cache.set(cache_key, result, ttl_hours=_AGGS_TTL)
        return result

    try:
        async with httpx.AsyncClient() as client:
            result = await _live_get_aggregates(client, eid, cycle)
    except Exception as e:
        print(f"[ftm]   aggregates failed for eid={eid} cycle={cycle}: {e!r}")
        result = []

    ai_cache.set(cache_key, result, ttl_hours=_AGGS_TTL)
    return result
