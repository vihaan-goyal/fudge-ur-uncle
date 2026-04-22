"""
FEC PAC contribution ingestion.

Pulls itemized PAC contributions from the OpenFEC API into the `donations`
table, replacing the fake data from seed.py for whichever legislators are
scoped in.

Usage (from project root):
    python -m backend.alerts.ingest_fec --state CT
    python -m backend.alerts.ingest_fec --bioguide M001169
    python -m backend.alerts.ingest_fec --state CT --days 180 --cycle 2026

Requires a data.gov API key set in backend/.env (same one congress_gov.py uses).
Falls back to DEMO_KEY (1000 req/hr, fine for testing).

Pipeline after ingestion:
    python -m backend.alerts.pipeline
"""

import argparse
import asyncio
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Make both "from backend.db" and "from api.openfec" resolvable, regardless
# of whether the caller runs this from project root or from backend/.
_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import httpx  # noqa: E402

from ..db import connect  # noqa: E402
from . import pac_classifier  # noqa: E402

# Import config lazily so running --help doesn't require .env to exist
def _load_config():
    import config  # type: ignore
    return config


# ---------- Low-level FEC client ----------

async def _fec_get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    """GET an OpenFEC endpoint with auth + retries."""
    cfg = _load_config()
    full_params = {**params, "api_key": cfg.DATA_GOV_API_KEY}
    url = f"{cfg.OPENFEC_BASE}{path}"
    for attempt in range(3):
        try:
            resp = await client.get(url, params=full_params, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"[fec]   rate limited, sleeping {wait}s")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if attempt == 2:
                raise
            print(f"[fec]   retry {attempt+1} after {e!r}")
            await asyncio.sleep(1)
    return {}


async def get_principal_committee(
    client: httpx.AsyncClient, candidate_id: str, target_cycle: int
) -> Optional[tuple[str, int]]:
    """Resolve a candidate FEC ID to their principal campaign committee ID.

    Strategy (try in order):
      1. /candidate/{id}/ scoped to target_cycle -> use principal_committees[0]
      2. /candidate/{id}/ unscoped -> pick most recent cycle <= target_cycle,
         re-fetch with that cycle filter, use principal_committees[0]
      3. /committee/?candidate_id={id} -> directly find committees linked to
         this candidate. Filter to type 'P' (principal campaign committee)
         and pick the most recent by last_file_date.

    Returns (committee_id, cycle_used) or None.
    """
    # --- Strategy 1: target cycle ---
    data = await _fec_get(
        client, f"/candidate/{candidate_id}/", {"cycle": target_cycle, "per_page": 1}
    )
    results = data.get("results", [])
    if results:
        committees = results[0].get("principal_committees") or []
        if committees and committees[0].get("committee_id"):
            return committees[0]["committee_id"], target_cycle

    # --- Strategy 2: unscoped, pick most recent active cycle <= target ---
    data = await _fec_get(client, f"/candidate/{candidate_id}/", {"per_page": 1})
    results = data.get("results", [])
    if results:
        cand = results[0]
        cycles = sorted([c for c in (cand.get("cycles") or []) if c <= target_cycle], reverse=True)
        for try_cycle in cycles[:3]:  # try the 3 most recent eligible cycles
            data2 = await _fec_get(
                client, f"/candidate/{candidate_id}/",
                {"cycle": try_cycle, "per_page": 1},
            )
            results2 = data2.get("results", [])
            if not results2:
                continue
            committees = results2[0].get("principal_committees") or []
            if committees and committees[0].get("committee_id"):
                if try_cycle != target_cycle:
                    print(f"[fec]     {candidate_id}: using cycle {try_cycle} "
                          f"(target {target_cycle} had no committee)")
                return committees[0]["committee_id"], try_cycle

    # --- Strategy 3: direct committee lookup (most permissive) ---
    data = await _fec_get(
        client, "/committees/",
        {"candidate_id": candidate_id, "per_page": 20, "sort": "-last_file_date"},
    )
    committees = data.get("results") or []
    # Prefer principal committees (type 'P'), then any active committee
    principals = [c for c in committees if c.get("committee_type") == "P"]
    pick = (principals or committees)
    if pick:
        # Get the most recent cycle this committee was active in
        cmte = pick[0]
        cmte_cycles = cmte.get("cycles") or []
        cycle_used = max([c for c in cmte_cycles if c <= target_cycle] or [target_cycle])
        cmte_id = cmte.get("committee_id")
        if cmte_id:
            print(f"[fec]     {candidate_id}: resolved via /committees/ -> "
                  f"{cmte_id} (cycle {cycle_used})")
            return cmte_id, cycle_used

    return None


async def fetch_pac_contributions(
    client: httpx.AsyncClient,
    committee_id: str,
    since: date,
    cycle: int,
    per_page: int = 100,
    max_pages: int = 5,
) -> list[dict]:
    """
    Fetch itemized PAC contributions to a committee for a cycle.

    Note on `since`: we do NOT pass min_date to the FEC API because Q1 reports
    have a multi-week processing lag. Instead, we sort by date desc, fetch
    the most recent records the cycle has, and filter client-side to those
    >= since. This way we always see whatever is the latest available data.

    Uses keyset pagination. Caps at max_pages to bound API calls.
    """
    params = {
        "committee_id": committee_id,
        "contributor_type": "committee",  # PAC -> committee transactions only
        "two_year_transaction_period": cycle,
        "sort": "-contribution_receipt_date",
        "per_page": per_page,
    }

    all_results: list[dict] = []
    for page in range(max_pages):
        data = await _fec_get(client, "/schedules/schedule_a/", params)
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)

        # Stop early if we've paged back past our cutoff date
        # (results are sorted desc, so once we see an old one we're done)
        last_date_str = results[-1].get("contribution_receipt_date") or ""
        if last_date_str:
            try:
                last_date = datetime.fromisoformat(
                    last_date_str.replace("Z", "")
                ).date()
                if last_date < since:
                    break
            except ValueError:
                pass

        pagination = data.get("pagination") or {}
        last_indexes = pagination.get("last_indexes") or {}
        if not last_indexes or len(results) < per_page:
            break
        # Keyset pagination for next page
        for key, val in last_indexes.items():
            params[key] = val

    # Client-side filter to since-cutoff
    filtered = []
    for r in all_results:
        d_str = r.get("contribution_receipt_date") or ""
        if not d_str:
            continue
        try:
            d = datetime.fromisoformat(d_str.replace("Z", "")).date()
        except ValueError:
            continue
        if d >= since:
            filtered.append(r)
    return filtered


# ---------- DB helpers ----------

def _existing_fec_ids(conn, bioguide_id: str) -> set[str]:
    """Return the set of fec_filing_ids already stored for a legislator (for dedup)."""
    rows = conn.execute(
        """SELECT fec_filing_id FROM donations
           WHERE bioguide_id = ? AND fec_filing_id IS NOT NULL""",
        (bioguide_id,),
    ).fetchall()
    return {r["fec_filing_id"] for r in rows}


def _insert_donation(conn, bioguide_id: str, record: dict, industry: str) -> bool:
    """Insert one FEC contribution as a donation row. Returns True if inserted."""
    pac_name = record.get("contributor_name") or "UNKNOWN"
    amount = record.get("contribution_receipt_amount") or 0.0
    d_str = record.get("contribution_receipt_date")
    sub_id = str(record.get("sub_id") or "")

    if amount <= 0 or not d_str or not sub_id:
        return False

    # Parse FEC's ISO-ish date (e.g. "2025-03-14T00:00:00")
    donation_date = datetime.fromisoformat(d_str.replace("Z", "")).date()

    try:
        conn.execute(
            """INSERT INTO donations
               (bioguide_id, pac_name, industry, amount, donation_date, fec_filing_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bioguide_id, pac_name, industry, amount, donation_date, sub_id),
        )
        return True
    except Exception as e:
        print(f"[fec]   insert failed for sub_id={sub_id}: {e}")
        return False


# ---------- Legislator resolution ----------

async def _resolve_legislators(
    bioguide: Optional[str], state: Optional[str]
) -> list[dict]:
    """Load legislators matching the CLI scope. Each has bioguide_id + fec_ids list."""
    from api import legislators as legs_mod
    all_legs = await legs_mod.fetch_legislators()

    def pick(leg: dict) -> Optional[dict]:
        ids = leg.get("id", {})
        bioguide_id = ids.get("bioguide")
        fec_ids = ids.get("fec") or []
        if not bioguide_id or not fec_ids:
            return None
        name = leg.get("name", {}).get("official_full", bioguide_id)
        return {"bioguide_id": bioguide_id, "fec_ids": fec_ids, "name": name, "terms": leg.get("terms", [])}

    scoped = []
    for leg in all_legs:
        picked = pick(leg)
        if not picked:
            continue
        if bioguide and picked["bioguide_id"] != bioguide:
            continue
        if state:
            current_state = (picked["terms"][-1] if picked["terms"] else {}).get("state")
            if current_state != state.upper():
                continue
        scoped.append(picked)
    return scoped


# ---------- Main ingestion ----------

async def ingest(
    bioguide: Optional[str] = None,
    state: Optional[str] = None,
    days: int = 365,
    cycles: Optional[list[int]] = None,
    max_pages_per_rep: int = 5,
) -> dict:
    """
    Ingest PAC contributions for one or more cycles.

    days defaults to 365 because FEC processing lag means recent-quarter data
    may not be available for several weeks; pulling a wider window catches
    enough data to run the pipeline meaningfully.

    cycles defaults to [current_year_rounded_to_even, current_year - 2] so
    we get both the current 2-year cycle AND the previous one (used as
    history for the anomaly baseline).
    """
    if cycles is None:
        # FEC two_year_transaction_period uses the EVEN year of each cycle
        this_year = date.today().year
        current_cycle = this_year if this_year % 2 == 0 else this_year + 1
        cycles = [current_cycle, current_cycle - 2]

    since = date.today() - timedelta(days=days)
    print(f"[fec] Pulling PAC contributions since {since}")
    print(f"[fec] Cycles to query: {cycles}")

    legislators = await _resolve_legislators(bioguide, state)
    if not legislators:
        print(f"[fec] No legislators matched. Check --bioguide/--state args.")
        return {"legislators": 0}
    print(f"[fec] Scope: {len(legislators)} legislator(s)")

    stats = {
        "legislators_processed": 0,
        "committees_resolved": 0,
        "api_pages_fetched": 0,
        "records_fetched": 0,
        "records_inserted": 0,
        "records_skipped_dupe": 0,
        "records_skipped_invalid": 0,
        "industry_breakdown": Counter(),
    }

    async with httpx.AsyncClient() as client:
        for leg in legislators:
            stats["legislators_processed"] += 1
            print(f"\n[fec] {leg['name']} ({leg['bioguide_id']}) - FEC IDs: {leg['fec_ids']}")

            with connect() as conn:
                existing = _existing_fec_ids(conn, leg["bioguide_id"])

            # Resolve committee: try ALL FEC IDs, pick the one with the
            # most recent resolved cycle (avoids picking a defunct old House
            # committee for a senator who switched chambers, like Murphy).
            attempts = []
            for fec_id in leg["fec_ids"]:
                attempt = await get_principal_committee(client, fec_id, max(cycles))
                if attempt:
                    attempts.append((fec_id, attempt[0], attempt[1]))
                    print(f"[fec]   {fec_id} -> committee={attempt[0]} (cycle {attempt[1]})")
                else:
                    print(f"[fec]   no committee resolvable for FEC ID {fec_id}")

            if not attempts:
                print(f"[fec]   SKIP: none of {leg['fec_ids']} resolved to a committee")
                continue

            # Pick the attempt with the most recent cycle
            attempts.sort(key=lambda a: a[2], reverse=True)
            fec_id, committee_id, cycle_used = attempts[0]
            stats["committees_resolved"] += 1
            if len(attempts) > 1:
                print(f"[fec]   USING fec_id={fec_id} (most recent cycle {cycle_used})")
            else:
                print(f"[fec]   USING fec_id={fec_id} -> committee={committee_id}")

            # Pull contributions across each requested cycle
            inserted_here = 0
            for cycle in cycles:
                records = await fetch_pac_contributions(
                    client, committee_id, since, cycle,
                    max_pages=max_pages_per_rep,
                )
                print(f"[fec]   cycle {cycle}: fetched {len(records)} records "
                      f"(after since-filter)")
                stats["records_fetched"] += len(records)

                with connect() as conn:
                    for rec in records:
                        sub_id = str(rec.get("sub_id") or "")
                        if sub_id in existing:
                            stats["records_skipped_dupe"] += 1
                            continue
                        industry = pac_classifier.classify(
                            rec.get("contributor_name") or ""
                        )
                        if _insert_donation(conn, leg["bioguide_id"], rec, industry):
                            stats["records_inserted"] += 1
                            stats["industry_breakdown"][industry] += 1
                            existing.add(sub_id)
                            inserted_here += 1
                        else:
                            stats["records_skipped_invalid"] += 1

            print(f"[fec]   inserted {inserted_here} new donation(s) total")

    # Summary
    print(f"\n[fec] ==== Ingestion summary ====")
    for k, v in stats.items():
        if k == "industry_breakdown":
            print(f"  industry_breakdown:")
            for ind, n in v.most_common():
                print(f"    {ind:28s} {n}")
        else:
            print(f"  {k}: {v}")
    return stats


# ---------- CLI ----------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest real FEC PAC contributions.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--bioguide", help="Ingest for one legislator (bioguide ID)")
    scope.add_argument("--state", help="Ingest for all legislators from a state (e.g. CT)")
    parser.add_argument("--days", type=int, default=365,
                        help="Lookback window in days (default: 365). FEC has "
                             "multi-week processing lag, so wider is safer.")
    parser.add_argument("--cycles", type=int, nargs="+", default=None,
                        help="Election cycles to query (default: current + previous). "
                             "FEC uses the EVEN year of each 2-year cycle, e.g. 2024 "
                             "covers 2023-2024.")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Max API pages per cycle per rep (default: 5 = up to 500 records)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.bioguide and not args.state:
        print("[fec] Warning: no scope. Defaulting to --state CT.")
        args.state = "CT"
    asyncio.run(ingest(
        bioguide=args.bioguide,
        state=args.state,
        days=args.days,
        cycles=args.cycles,
        max_pages_per_rep=args.max_pages,
    ))


if __name__ == "__main__":
    main()