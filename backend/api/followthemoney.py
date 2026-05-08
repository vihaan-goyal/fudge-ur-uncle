"""
FollowTheMoney (NIMP) API wrapper - state campaign-finance aggregates.

Powers `/api/state-alerts/*`. The free tier is generous but the docs are
notoriously cryptic — every request takes a `gro` (group), various filter
prefixes, and `dataset` (candidates|contributions|...). The endpoint
constants below are verified against the live API.

Public functions:
  - find_candidate_eid(name, state, chamber, party) -> (eid, confidence) | None
  - get_industry_aggregates(eid) -> list[{industry_name, amount, n_records}]

Both go through ai_cache because the free tier's monthly cap is real and
aggregates barely move within a cycle.

Falls back to SAMPLE_FTM_DATA when:
  - FTM_API_KEY is not set, OR
  - upstream returns an error / unrecognized shape

This mirrors the legiscan.py / news.py / guardian.py pattern of "always
return something usable so the demo runs even without keys."

## Verified API shape (2026-05, against live FTM)

Industry breakdown of donations RECEIVED by a candidate:
    GET https://api.followthemoney.org/?
        APIKey=...&mode=json&
        dataset=contributions&
        gro=d-cci&            # group by Contributor General Industry
        c-t-eid=<EID>         # filter to donations TO this candidate
Returns rows like:
    {"General_Industry": "Pharmaceuticals & Health Products",
     "Broad_Sector": "Health",
     "#_of_Records": "104",
     "Total_$": "1517848.49"}

Profile lookup:
    GET https://api.followthemoney.org/entity.php?eid=<EID>&APIKey=...&mode=json
Returns {data: {overview, AsCandidate, AsContributor, Relationships}}.
overview.industry has employer/CatCode history; AsCandidate/AsContributor
are summary stubs whose `request` field is the URL-fragment for follow-up.

## Known limitations

1. **No cycle filter on grouped contributions.** `y=`, `f-y=`, `f-y-y=`
   all return 0 records when combined with grouping. FTM's grouped-
   aggregate endpoint is lifetime-only. Per-cycle breakdown would require
   pulling itemized rows and grouping client-side, which would burn the
   monthly quota fast.

2. **State filter for candidate enumeration is undocumented.** None of
   `s-y-st`, `s`, `c-r-s`, `c-t-s`, `c-r-osj` honor a state filter on the
   candidates dataset, so live enumeration of "all CT state legislators"
   isn't reliable. Workaround: a curated CSV directory at
   `backend/data/ftm_eids.csv` (loaded by `api/ftm_directory.py`) maps
   (state, chamber, name) -> eid offline. `find_candidate_eid` checks
   that directory before the live API; SAMPLE_FTM_EIDS remains as the
   final no-key fallback. See _live_find_eid TODO below.

3. **Industry strings are FTM/CRP names, not Catcodes.** The `gro=d-cci`
   grouping returns `General_Industry` strings (e.g. "Oil & Gas"). The
   ingester translates these via `catcode_map.industry_for_ftm_name`.
   Buckets like "Candidate Contributions" (self-funding), "Uncoded",
   "Public Subsidy", "Retired" are mapped to `_ignore` and dropped.
"""
import asyncio
from difflib import SequenceMatcher
from typing import Optional

import httpx

from config import FTM_API_KEY  # type: ignore
from api import ai_cache
from api import ftm_directory

_TIMEOUT = 20.0
_FTM_BASE = "https://api.followthemoney.org/"
_FTM_ENTITY = "https://api.followthemoney.org/entity.php"

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
    ("CT", "Martin Looney"): "13011269",
    ("CT", "Matt Ritter"): "6508453",
}

# Keyed by eid only (FTM aggregates are lifetime, not per-cycle).
# Returns list[{industry_name, amount, n_records}] using FTM-style names
# so the live and sample paths share the same downstream mapping.
_LOONEY_AGG = [
    {"industry_name": "Pharmaceuticals & Health Products", "amount": 35_000.0, "n_records": 11},
    {"industry_name": "Health Services/HMOs", "amount": 18_000.0, "n_records": 6},
    {"industry_name": "Oil & Gas", "amount": 22_000.0, "n_records": 8},
    {"industry_name": "Commercial Banks", "amount": 12_500.0, "n_records": 5},
    {"industry_name": "Public Sector Unions", "amount": 45_000.0, "n_records": 22},
]
_RITTER_AGG = [
    {"industry_name": "Oil & Gas", "amount": 18_000.0, "n_records": 7},
    {"industry_name": "Pharmaceuticals & Health Products", "amount": 22_000.0, "n_records": 9},
    {"industry_name": "Insurance", "amount": 9_500.0, "n_records": 4},
]
SAMPLE_FTM_AGGREGATES = {
    "13011269": _LOONEY_AGG,  # LOONEY, MARTIN M (CT)
    "6508453": _RITTER_AGG,   # RITTER, MATTHEW D (CT)
}


# ---- Low-level HTTP -------------------------------------------------

class FTMUpstreamError(RuntimeError):
    """FTM responded but the response wasn't usable (quota error, etc.)."""


async def _ftm_get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    """GET against FTM with the API key attached. Retries 429 with backoff.

    FTM's free tier returns HTTP 200 with {"error": "..."} when the monthly
    quota is exhausted, instead of a 4xx. We raise FTMUpstreamError on that
    so callers can distinguish "real empty" from "upstream wedged" — and
    avoid caching the empty response under the live cache key.
    """
    if not FTM_API_KEY:
        raise RuntimeError("FTM_API_KEY not set")
    full = {**params, "APIKey": FTM_API_KEY, "mode": "json"}
    for attempt in range(3):
        try:
            resp = await client.get(url, params=full, timeout=_TIMEOUT)
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                raise FTMUpstreamError(str(data["error"]))
            return data
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            if attempt == 2:
                raise
            await asyncio.sleep(1)
    raise FTMUpstreamError("retries exhausted")


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

    TODO: state-filter syntax is unclear — none of the obvious tokens
    (`s-y-st`, `s`, `c-r-s`, `c-t-s`, `c-r-osj`) honor a state filter on
    the /?dataset=candidates&gro=c-t-id endpoint, and bare `search=name`
    returns a global summary. Until we get clarity from FTM docs, this
    returns None on live calls and the caller falls through to sample
    data. The fix is probably to download FTM's static entity directory
    and do name matching client-side, but that's a bigger change.
    """
    return None


async def find_candidate_eid(
    name: str, state: str, chamber: str, party: Optional[str] = None
) -> Optional[tuple[str, float]]:
    """Return (FTM eid, match confidence) for a state legislator, or None if no good match.

    Resolution order:
      1. ai_cache hit (empty list = cached "no match")
      2. Offline directory CSV (backend/data/ftm_eids.csv) — curated, key-free
      3. Live FTM candidates search (currently a stub returning None)
      4. SAMPLE_FTM_EIDS — final no-key demo fallback

    Confidence is the SequenceMatcher ratio between the requested name and
    the name on the matched record; below `_MIN_MATCH_CONFIDENCE` we discard
    rather than risk attributing donations to the wrong person.
    """
    cache_key = f"ftm:eid:{state.upper()}:{chamber.lower()}:{name.lower().strip()}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        # Empty list = cached "no match"; non-empty list = cached [eid, confidence].
        return tuple(cached) if cached else None  # type: ignore[return-value]

    # Try the offline directory first — works without a key, and a curated
    # match is as authoritative as a live lookup.
    directory_match = ftm_directory.lookup(name, state, chamber)
    if directory_match:
        ai_cache.set(cache_key, list(directory_match), ttl_hours=_EID_TTL)
        return directory_match

    if FTM_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                result = await _live_find_eid(client, name, state, chamber, party)
        except Exception as e:
            print(f"[ftm]   eid lookup failed for {name} ({state}/{chamber}): {e!r}")
            result = None
        if result:
            ai_cache.set(cache_key, list(result), ttl_hours=_EID_TTL)
            return result

    # Final fallback: hardcoded sample data so the demo path stays alive.
    sample = _lookup_sample_eid(name, state)
    ai_cache.set(cache_key, list(sample) if sample else [], ttl_hours=_EID_TTL)
    return sample


# ---- Industry aggregates --------------------------------------------

async def _live_get_aggregates(client: httpx.AsyncClient, eid: str) -> list[dict]:
    """Pull the candidate's industry breakdown — lifetime, not per-cycle.

    Live request shape (verified):
      dataset=contributions
      gro=d-cci             (group by Contributor General Industry)
      c-t-eid=<EID>         (filter: donations TO this candidate)

    Returns rows shaped {industry_name: str, amount: float, n_records: int}.
    The `industry_name` is FTM's CRP-derived `General_Industry` string,
    e.g. "Pharmaceuticals & Health Products". Translate downstream via
    `catcode_map.industry_for_ftm_name`.
    """
    params = {
        "dataset": "contributions",
        "gro": "d-cci",
        "c-t-eid": eid,
    }
    data = await _ftm_get(client, _FTM_BASE, params)
    records = data.get("records") or data.get("Records") or []
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        # Each value is a small dict like {"General_Industry": "Oil & Gas"} OR
        # the raw string — handle both.
        gi = r.get("General_Industry")
        if isinstance(gi, dict):
            industry_name = gi.get("General_Industry") or gi.get("name") or ""
        else:
            industry_name = gi or ""

        recs = r.get("#_of_Records")
        if isinstance(recs, dict):
            n_raw = recs.get("#_of_Records") or recs.get("n_records") or 0
        else:
            n_raw = recs or 0

        total = r.get("Total_$")
        if isinstance(total, dict):
            t_raw = total.get("Total_$") or total.get("total") or 0
        else:
            t_raw = total or 0

        if not industry_name:
            continue
        try:
            amount = float(str(t_raw).replace(",", "").replace("$", "")) or 0.0
        except ValueError:
            amount = 0.0
        if amount <= 0:
            continue
        try:
            n_records = int(str(n_raw).replace(",", ""))
        except ValueError:
            n_records = 0
        out.append({
            "industry_name": str(industry_name).strip(),
            "amount": amount,
            "n_records": n_records,
        })
    return out


async def get_industry_aggregates(eid: str) -> list[dict]:
    """Lifetime industry breakdown for one candidate.

    Returns list[{industry_name: str, amount: float, n_records: int}].
    FTM grouped-aggregate endpoints are lifetime-only — see module docstring.
    """
    cache_key = f"ftm:aggs:{eid}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    if not FTM_API_KEY:
        result = SAMPLE_FTM_AGGREGATES.get(eid, [])
        ai_cache.set(cache_key, result, ttl_hours=_AGGS_TTL)
        return result

    live_failed = False
    try:
        async with httpx.AsyncClient() as client:
            result = await _live_get_aggregates(client, eid)
    except Exception as e:
        print(f"[ftm]   aggregates failed for eid={eid}: {e!r}")
        result = []
        live_failed = True

    # Don't cache (or sample-pad) a transient live failure under the same key
    # as a real result — that pinned demo numbers for 24h after every hiccup,
    # masking the outage from the next caller. Only persist a successful
    # response; let the next attempt re-hit the wire.
    if live_failed:
        return SAMPLE_FTM_AGGREGATES.get(eid, [])

    ai_cache.set(cache_key, result, ttl_hours=_AGGS_TTL)
    return result
