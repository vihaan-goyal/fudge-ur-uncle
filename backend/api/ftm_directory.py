"""
Offline FTM eid directory — name-based lookup against a curated CSV.

Why this exists: FollowTheMoney's candidates-search API has no documented
state-filter syntax (see backend/api/followthemoney.py module docstring),
so enumerating "all CT state legislators" via the live API isn't reliable.
The pragmatic alternative is a static lookup table built by hand from
FTM's website exports — populated as needed, matched against Legiscan
roster names with the same fuzzy ratio used elsewhere in the codebase.

CSV location: backend/data/ftm_eids.csv with columns:
    state,chamber,name,eid
- state:   2-letter USPS code (matches Legiscan)
- chamber: 'Senate' or 'House' (matches Legiscan's chamber field)
- name:    legislator's full name as listed on FTM
- eid:     FollowTheMoney Entity ID

Adding more rows (manual but lightweight):
  1. https://www.followthemoney.org/show-me — filter by state + office
  2. Open the candidate's Entity Details page, copy the eid from the URL
  3. Append a (state, chamber, name, eid) row to backend/data/ftm_eids.csv

Missing or empty file -> empty index -> caller falls through to the
SAMPLE_FTM_EIDS dict in followthemoney.py.
"""
import csv
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# Mirror of _MIN_MATCH_CONFIDENCE in followthemoney.py — keep them in sync.
# Below this confidence we drop the result rather than risk attributing
# donations to the wrong person.
_MIN_MATCH_CONFIDENCE = 0.78

_CSV_PATH = Path(__file__).parent.parent / "data" / "ftm_eids.csv"

# Lazy-loaded index keyed by uppercase state code.
# Each value: list of (name, chamber, eid).
_index: Optional[dict[str, list[tuple[str, str, str]]]] = None


def _load() -> dict[str, list[tuple[str, str, str]]]:
    global _index
    if _index is not None:
        return _index
    idx: dict[str, list[tuple[str, str, str]]] = {}
    if not _CSV_PATH.exists():
        _index = idx
        return idx
    try:
        with _CSV_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = (row.get("state") or "").strip().upper()
                chamber = (row.get("chamber") or "").strip()
                name = (row.get("name") or "").strip()
                eid = (row.get("eid") or "").strip()
                if not (state and name and eid):
                    continue
                idx.setdefault(state, []).append((name, chamber, eid))
    except Exception as e:
        print(f"[ftm_directory] failed to load {_CSV_PATH}: {e!r}")
    _index = idx
    return idx


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def lookup(
    name: str, state: str, chamber: Optional[str] = None
) -> Optional[tuple[str, float]]:
    """Best fuzzy match for (name, state[, chamber]) in the directory.

    If chamber is provided AND any directory entry in that state shares the
    chamber, matching is restricted to those rows — protects against
    same-name reps in different chambers. If no chamber rows match, falls
    back to all entries in the state.

    Returns (eid, confidence) when the best match meets _MIN_MATCH_CONFIDENCE,
    otherwise None.
    """
    entries = _load().get(state.upper(), [])
    if not entries:
        return None

    if chamber:
        chamber_l = chamber.strip().lower()
        same_chamber = [(n, c, e) for (n, c, e) in entries if c.lower() == chamber_l]
        if same_chamber:
            entries = same_chamber

    best: Optional[tuple[str, float]] = None
    for (n, _c, eid) in entries:
        conf = _name_similarity(name, n)
        if best is None or conf > best[1]:
            best = (eid, conf)

    if best and best[1] >= _MIN_MATCH_CONFIDENCE:
        return best
    return None


def reload() -> int:
    """Force a re-read from disk. Returns the number of state buckets loaded."""
    global _index
    _index = None
    return len(_load())
