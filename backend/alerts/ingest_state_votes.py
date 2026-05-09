"""
State "upcoming vote" feed - active bills -> scheduled_votes.

State legislatures don't publish a clean scheduled-vote calendar like
Congress.gov does, so we approximate "imminent vote" with bill *status*:
a bill that's been engrossed (passed one chamber) is heading to a floor
vote in the other chamber within days/weeks. See `legiscan.get_active_bills`
for the masterlist filter.

Date semantics differ from federal:
  - Federal `scheduled_votes.scheduled_date` = real upcoming floor-vote date.
  - State `scheduled_votes.scheduled_date` = bill's `status_date` plus a
    forecast offset (days from engrossment to second-chamber vote).

The forecast offset means the alert scoring formula's V (vote-proximity)
treats a recently-engrossed bill the same way it treats a federal bill
scheduled in N days — high V when fresh, decaying as the bill stalls.

Usage (from project root):
    python -m backend.alerts.ingest_state_votes --state CT
    python -m backend.alerts.ingest_state_votes --state CT --dry-run

Falls back to legiscan.SAMPLE_ACTIVE_BILLS when no LEGISCAN_API_KEY is
set, so the pipeline can be exercised end-to-end in dev.
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

try:
    from ..db import connect  # noqa: E402
except ImportError:
    from db import connect  # noqa: E402
from .state_categories import categorize  # noqa: E402

from api import legiscan  # type: ignore  # noqa: E402


# Days from engrossment to the receiving chamber's floor vote, on average.
# Used to project a forward-looking `scheduled_date` so the existing
# scoring formula's V signal works without per-jurisdiction logic.
DEFAULT_VOTE_LEAD_DAYS = 14


def _parse_status_date(s: str) -> date | None:
    """Legiscan returns dates like '2025-04-12'. Tolerate empties/garbage."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, TypeError):
        return None


def _scheduled_date_for(bill: dict, lead_days: int) -> date | None:
    """Project a synthetic forward-looking floor-vote date for a state bill.

    bill["status_date"] is when the bill became engrossed; the receiving
    chamber typically votes within `lead_days` days of that. If the
    projected date is already in the past (stalled bill), bump it to today
    so V (vote-proximity) doesn't go to zero — the bill IS still pending.
    """
    base = _parse_status_date(bill.get("status_date") or "")
    if not base:
        return None
    projected = base + timedelta(days=lead_days)
    today = date.today()
    return projected if projected >= today else today


def _upsert_scheduled_vote(
    conn, state: str, bill: dict, category: str, scheduled_date: date
) -> bool:
    """Insert or update a state scheduled_votes row. Returns True if inserted."""
    bill_number = bill.get("number") or f"BILL-{bill.get('bill_id')}"
    title = bill.get("title") or ""
    chamber = (bill.get("chamber") or "state").lower()

    existing = conn.execute(
        """SELECT id FROM scheduled_votes
           WHERE jurisdiction = 'state' AND state_code = ? AND bill_number = ?""",
        (state, bill_number),
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
           VALUES ('state', ?, ?, ?, ?, ?, ?)""",
        (state, bill_number, title, category, scheduled_date, chamber),
    )
    return True


async def ingest_state_votes(
    state: str, lead_days: int = DEFAULT_VOTE_LEAD_DAYS, dry_run: bool = False
) -> dict:
    """Pull active bills for one state, classify by topic, write to scheduled_votes."""
    state = state.upper()
    bills = await legiscan.get_active_bills(state)
    print(f"[state-votes] {state}: {len(bills)} engrossed bill(s) returned by Legiscan")

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
            print(f"[state-votes]   would write: {bill.get('number')} ({category}) -> {sched.isoformat()}")
            continue
        bill_number = bill.get("number") or f"BILL-{bill.get('bill_id')}"
        keepers.append(bill_number)
        with connect() as conn:
            inserted = _upsert_scheduled_vote(conn, state, bill, category, sched)
        if inserted:
            stats["rows_inserted"] += 1
            print(f"[state-votes]   + {bill.get('number')} ({category}, sched={sched.isoformat()}) {bill.get('title','')[:60]}")
        else:
            stats["rows_updated"] += 1

    # Purge stale rows: bills that previously fell into a category but no longer
    # do (re-categorization), and bills that have dropped off the masterlist
    # (passed/failed). Without this, false-positive categorizations from older
    # ingest passes — and bills that are no longer pending — would linger
    # forever and keep generating alerts.
    if not dry_run and keepers:
        placeholders = ",".join("?" * len(keepers))
        with connect() as conn:
            stale_ids = [
                r["id"] for r in conn.execute(
                    f"""SELECT id FROM scheduled_votes
                        WHERE jurisdiction = 'state'
                          AND state_code = ?
                          AND bill_number NOT IN ({placeholders})""",
                    (state, *keepers),
                ).fetchall()
            ]
            if stale_ids:
                stale_placeholders = ",".join("?" * len(stale_ids))
                cur = conn.execute(
                    f"DELETE FROM alerts WHERE actor_type = 'state' AND vote_id IN ({stale_placeholders})",
                    stale_ids,
                )
                stats["alerts_purged"] = cur.rowcount
                cur = conn.execute(
                    f"DELETE FROM scheduled_votes WHERE id IN ({stale_placeholders})",
                    stale_ids,
                )
                stats["rows_purged"] = cur.rowcount

    print(f"[state-votes] Done. Stats: {stats}")
    return stats


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", required=True, help="2-letter state code (e.g. CT)")
    p.add_argument("--lead-days", type=int, default=DEFAULT_VOTE_LEAD_DAYS,
                   help=f"Engrossment->vote lead time projection (default: {DEFAULT_VOTE_LEAD_DAYS})")
    p.add_argument("--dry-run", action="store_true", help="Print what would be written")
    args = p.parse_args()

    asyncio.run(ingest_state_votes(state=args.state, lead_days=args.lead_days, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
