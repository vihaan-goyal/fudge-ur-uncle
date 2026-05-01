"""
FollowTheMoney ingestion - state campaign-finance aggregates -> donations.

Mirror of `ingest_fec.py` for the state side. The FEC version pulls itemized
PAC contributions; FTM's free tier exposes aggregates by industry per
candidate per cycle, so each `donations` row from FTM represents a *bucket*
("$24k from oil & gas in cycle 2024") rather than a single PAC's check.

Pipeline per state legislator:
  1. Pull the cached Legiscan roster for the state -> list of state reps
  2. For each rep: resolve their FTM eid (cached in `external_ids`)
  3. For each (rep, cycle): get industry aggregates from FTM
  4. Translate Catcode -> our industry name, write to `donations` with
     actor_type='state', actor_id=people_id

Usage (from project root):
    python -m backend.alerts.ingest_ftm --state CT
    python -m backend.alerts.ingest_ftm --state CT --cycle 2024
    python -m backend.alerts.ingest_ftm --state CT --people-id 9001

Falls back to FTM's sample data when FTM_API_KEY is unset (matches the
rest of `backend/api/*.py`). Run `python -m backend.db` first to make
sure `external_ids` exists.
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# Resolve both `from backend.x` and `from api.x` import styles regardless of CWD.
_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ..db import connect  # noqa: E402
from .catcode_map import industry_for_catcode  # noqa: E402

from api import followthemoney as ftm  # type: ignore  # noqa: E402
from api import legiscan  # type: ignore  # noqa: E402


# ---- external_ids helpers -------------------------------------------

def _stored_eid(conn, people_id: str) -> tuple[str | None, float | None]:
    """Return the cached (eid, confidence) for a state actor, or (None, None)."""
    row = conn.execute(
        """SELECT external_id, confidence FROM external_ids
           WHERE actor_type = 'state' AND actor_id = ? AND source = 'ftm'""",
        (people_id,),
    ).fetchone()
    if not row:
        return None, None
    return row["external_id"], row["confidence"]


def _store_eid(conn, people_id: str, eid: str, confidence: float) -> None:
    conn.execute(
        """INSERT INTO external_ids (actor_type, actor_id, source, external_id, confidence)
           VALUES ('state', ?, 'ftm', ?, ?)
           ON CONFLICT(actor_type, actor_id, source) DO UPDATE SET
             external_id = excluded.external_id,
             confidence = excluded.confidence,
             matched_at = CURRENT_TIMESTAMP""",
        (people_id, eid, confidence),
    )


# ---- donations write helpers ----------------------------------------

def _existing_ftm_filing_ids(conn, people_id: str) -> set[str]:
    """fec_filing_id is reused as the FTM bucket key: 'FTM:{eid}:{cycle}:{catcode}'."""
    rows = conn.execute(
        """SELECT fec_filing_id FROM donations
           WHERE actor_type = 'state' AND actor_id = ? AND fec_filing_id LIKE 'FTM:%'""",
        (people_id,),
    ).fetchall()
    return {r["fec_filing_id"] for r in rows}


def _insert_aggregate_donation(
    conn,
    people_id: str,
    eid: str,
    cycle: int,
    catcode: str,
    amount: float,
    n_records: int,
    industry: str,
) -> bool:
    """Insert one industry-aggregate row. Returns True if inserted."""
    filing_id = f"FTM:{eid}:{cycle}:{catcode}"
    pac_name = f"{industry.replace('_', ' ').title()} industry (FTM aggregate, {n_records} records)"
    # Date semantics for an aggregate that covers a 2-year cycle:
    #  - Current/future cycle: it's the latest-available data, treat as "today"
    #    so the pipeline's R (recency) signal stays high and the row stays
    #    inside the donation_lookback window.
    #  - Past cycle: use cycle midpoint, truthfully old; will drop out of
    #    the lookback window naturally.
    today = date.today()
    current_cycle = today.year if today.year % 2 == 0 else today.year - 1
    proxy_date = today if cycle >= current_cycle else date(cycle, 6, 30)
    try:
        conn.execute(
            """INSERT INTO donations
               (actor_type, actor_id, pac_name, industry, amount, donation_date, fec_filing_id)
               VALUES ('state', ?, ?, ?, ?, ?, ?)""",
            (people_id, pac_name, industry, amount, proxy_date, filing_id),
        )
        return True
    except Exception as e:
        print(f"[ftm]   insert failed for {filing_id}: {e}")
        return False


# ---- Main ingest ----------------------------------------------------

async def _resolve_state_actors(state: str, only_people_id: str | None) -> list[dict]:
    """Pull the Legiscan roster and reduce to dicts the ingester needs.

    Skips Legiscan's committee pseudo-entries (rows like "Judiciary Committee"
    that appear with chamber=='' / no district) — they aren't real people.
    """
    roster = await legiscan.get_state_legislators(state)
    out = []
    for rep in roster:
        people_id = str(rep.get("people_id") or "")
        chamber = rep.get("chamber") or ""
        name = rep.get("name") or ""
        if not people_id:
            continue
        if "committee" in name.lower():
            continue
        if chamber not in ("Senate", "House"):
            continue
        if only_people_id and people_id != only_people_id:
            continue
        out.append({
            "people_id": people_id,
            "name": name,
            "party": rep.get("party") or "",
            "chamber": chamber,
        })
    return out


async def ingest_state(
    state: str, cycle: int, only_people_id: str | None = None, dry_run: bool = False
) -> dict:
    """Pull FTM aggregates for one state's legislators in one cycle."""
    state = state.upper()
    actors = await _resolve_state_actors(state, only_people_id)
    print(f"[ftm] State {state}: {len(actors)} legislator(s) in scope, cycle={cycle}")

    stats = {"actors": len(actors), "eids_resolved": 0, "rows_inserted": 0, "rows_skipped": 0}

    # Open and close the connection per-actor: holding one across every `await`
    # blocks ai_cache writes and serializes the whole run.
    for actor in actors:
        people_id = actor["people_id"]

        # 1. Resolve FTM eid (use cached if present)
        with connect() as conn:
            eid, conf = _stored_eid(conn, people_id)
        if not eid:
            match = await ftm.find_candidate_eid(
                actor["name"], state, actor["chamber"], actor["party"]
            )
            if not match:
                print(f"[ftm]   no FTM match for {actor['name']} ({people_id})")
                continue
            eid, conf = match
            if not dry_run:
                with connect() as conn:
                    _store_eid(conn, people_id, eid, conf)
        stats["eids_resolved"] += 1
        print(f"[ftm]   {actor['name']} -> FTM eid={eid} (conf={conf:.2f})")

        # 2. Pull industry aggregates
        aggs = await ftm.get_industry_aggregates(eid, cycle)
        if not aggs:
            print(f"[ftm]     no aggregates for cycle {cycle}")
            continue

        # 3. Insert each as a donation row
        with connect() as conn:
            existing = _existing_ftm_filing_ids(conn, people_id)
            for a in aggs:
                catcode = a["catcode"]
                filing_id = f"FTM:{eid}:{cycle}:{catcode}"
                if filing_id in existing:
                    stats["rows_skipped"] += 1
                    continue
                industry = industry_for_catcode(catcode)
                if dry_run:
                    print(f"[ftm]     would insert: {industry} ${a['amount']:,.0f} ({catcode})")
                    continue
                if _insert_aggregate_donation(
                    conn, people_id, eid, cycle, catcode, a["amount"], a["n_records"], industry
                ):
                    stats["rows_inserted"] += 1

    print(f"[ftm] Done. Stats: {stats}")
    return stats


def _default_cycle() -> int:
    """Even-year is the dominant state-cycle convention (CT included)."""
    y = date.today().year
    return y if y % 2 == 0 else y - 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", required=True, help="2-letter state code (e.g. CT)")
    p.add_argument("--cycle", type=int, default=_default_cycle(),
                   help=f"Election cycle year (default: {_default_cycle()})")
    p.add_argument("--people-id", help="Restrict to a single Legiscan people_id")
    p.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = p.parse_args()

    asyncio.run(ingest_state(
        state=args.state, cycle=args.cycle,
        only_people_id=args.people_id, dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
