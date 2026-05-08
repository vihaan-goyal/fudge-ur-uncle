"""
Federal "upcoming vote" feed — active bills -> scheduled_votes.

Mirrors `ingest_state_votes.py`, but for Congress.gov. There's no clean
"upcoming floor vote" endpoint at /v3/, so we use bill *status* as a proxy:
a bill that's been reported out of committee, placed on the calendar, or
passed one chamber and is pending the other is a reasonable signal of
imminent floor action. See `congress_gov.get_active_bills` for the
filter-text patterns.

This replaces the deprecated workflow of editing `seed.py` to bump the
hand-curated bill dates each demo. **The two are mutually exclusive**:
running this ingester after `python -m backend.alerts.seed` will purge the
seed bills (they won't be in the live keepers list). Pick one source.

Date semantics match the state ingester:
  - `scheduled_date` = bill's `status_date` plus a forecast offset.
  - Past projections get bumped to today so V (vote-proximity) doesn't
    collapse to zero on stalled-but-still-pending bills.

Usage (from project root):
    python -m backend.alerts.ingest_federal_votes
    python -m backend.alerts.ingest_federal_votes --congress 119 --dry-run

Falls back to congress_gov.SAMPLE_ACTIVE_BILLS when no DATA_GOV_API_KEY is
set so the pipeline can be exercised end-to-end in dev.
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ..db import connect  # noqa: E402
from .state_categories import categorize  # noqa: E402

from api import congress_gov  # type: ignore  # noqa: E402


# Days from "reported / engrossed / received in other chamber" to the
# floor vote, on average. Picked to match the state-side default so V
# behaves consistently across jurisdictions.
DEFAULT_VOTE_LEAD_DAYS = 14

# Default Congress number. Bumping this between sessions is cheap; we
# don't auto-detect because the API has no "current congress" endpoint.
DEFAULT_CONGRESS = 119


def _parse_status_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, TypeError):
        return None


def _scheduled_date_for(bill: dict, lead_days: int) -> date | None:
    """Project a synthetic forward-looking floor-vote date.

    `bill["status_date"]` is the date of the latestAction (committee report,
    calendar placement, etc.). Floor consideration typically follows within
    `lead_days`. If the projected date is already past — bill stalled but
    still pending — bump to today so V stays meaningful.
    """
    base = _parse_status_date(bill.get("status_date") or "")
    if not base:
        return None
    projected = base + timedelta(days=lead_days)
    today = date.today()
    return projected if projected >= today else today


def _upsert_scheduled_vote(
    conn, bill: dict, category: str, scheduled_date: date
) -> bool:
    """Insert or update a federal scheduled_votes row. Returns True if inserted."""
    bill_number = bill.get("number") or f"BILL-{bill.get('bill_id')}"
    title = bill.get("title") or ""
    chamber = (bill.get("chamber") or "senate").lower()

    existing = conn.execute(
        """SELECT id FROM scheduled_votes
           WHERE jurisdiction = 'federal' AND state_code IS NULL AND bill_number = ?""",
        (bill_number,),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE scheduled_votes
               SET title = ?, category = ?, scheduled_date = ?, chamber = ?
               WHERE id = ?""",
            (title, category, scheduled_date, chamber, existing["id"]),
        )
        return False

    conn.execute(
        """INSERT INTO scheduled_votes
           (jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber)
           VALUES ('federal', NULL, ?, ?, ?, ?, ?)""",
        (bill_number, title, category, scheduled_date, chamber),
    )
    return True


async def ingest_federal_votes(
    congress: int = DEFAULT_CONGRESS,
    lead_days: int = DEFAULT_VOTE_LEAD_DAYS,
    dry_run: bool = False,
) -> dict:
    """Pull recently-active federal bills, classify, and write to scheduled_votes."""
    bills = await congress_gov.get_active_bills(congress=congress)
    print(f"[federal-votes] congress {congress}: {len(bills)} active bill(s) returned by Congress.gov")

    stats = {
        "bills_considered": len(bills),
        "uncategorized_skipped": 0,
        "stale_status_skipped": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_purged": 0,
        "alerts_purged": 0,
    }

    if not bills:
        return stats

    keepers: list[str] = []
    for bill in bills:
        sched = _scheduled_date_for(bill, lead_days)
        if not sched:
            stats["stale_status_skipped"] += 1
            continue
        category = categorize(bill.get("title") or "")
        if not category:
            stats["uncategorized_skipped"] += 1
            continue
        if dry_run:
            print(f"[federal-votes]   would write: {bill.get('number')} ({category}) -> {sched.isoformat()}")
            continue
        bill_number = bill.get("number") or f"BILL-{bill.get('bill_id')}"
        keepers.append(bill_number)
        with connect() as conn:
            inserted = _upsert_scheduled_vote(conn, bill, category, sched)
        if inserted:
            stats["rows_inserted"] += 1
            print(f"[federal-votes]   + {bill.get('number')} ({category}, sched={sched.isoformat()}) {bill.get('title','')[:60]}")
        else:
            stats["rows_updated"] += 1

    # Purge stale rows: bills that previously matched a category but no
    # longer do (re-categorization), and bills that have dropped off the
    # active list (passed/failed). The keepers-non-empty guard guarantees
    # an upstream wedge or quota error doesn't nuke the whole table.
    #
    # NOTE: this also removes seed.py's hand-curated rows once a real
    # ingest has populated the table. Use one source or the other, not both.
    if not dry_run and keepers:
        placeholders = ",".join("?" * len(keepers))
        with connect() as conn:
            stale_ids = [
                r["id"] for r in conn.execute(
                    f"""SELECT id FROM scheduled_votes
                        WHERE jurisdiction = 'federal'
                          AND state_code IS NULL
                          AND bill_number NOT IN ({placeholders})""",
                    keepers,
                ).fetchall()
            ]
            if stale_ids:
                stale_placeholders = ",".join("?" * len(stale_ids))
                cur = conn.execute(
                    f"DELETE FROM alerts WHERE actor_type = 'federal' AND vote_id IN ({stale_placeholders})",
                    stale_ids,
                )
                stats["alerts_purged"] = cur.rowcount
                cur = conn.execute(
                    f"DELETE FROM scheduled_votes WHERE id IN ({stale_placeholders})",
                    stale_ids,
                )
                stats["rows_purged"] = cur.rowcount

    print(f"[federal-votes] Done. Stats: {stats}")
    return stats


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--congress", type=int, default=DEFAULT_CONGRESS,
                   help=f"Congress number (default: {DEFAULT_CONGRESS})")
    p.add_argument("--lead-days", type=int, default=DEFAULT_VOTE_LEAD_DAYS,
                   help=f"Status->vote lead time projection (default: {DEFAULT_VOTE_LEAD_DAYS})")
    p.add_argument("--dry-run", action="store_true", help="Print what would be written")
    args = p.parse_args()

    asyncio.run(ingest_federal_votes(
        congress=args.congress, lead_days=args.lead_days, dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
