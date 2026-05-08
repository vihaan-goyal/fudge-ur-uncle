"""
End-to-end alerts refresh: federal ingest + state ingest + pipeline.

This is the cron-friendly entrypoint. It chains the three commands you'd
otherwise run by hand:

    python -m backend.alerts.ingest_federal_votes
    python -m backend.alerts.ingest_state_votes --state CT     (per state)
    python -m backend.alerts.pipeline

Failure isolation: if an ingester errors (upstream wedge, quota hit, network
blip), we log it and continue — the pipeline still runs against whatever
rows are already in the DB. The pipeline's own failure is treated as fatal
because that's the signal a cron job should care about.

Exit codes:
    0   pipeline ran (regardless of ingester hiccups)
    1   pipeline raised, or arguments were invalid

Usage (from project root):
    python -m backend.alerts.refresh
    python -m backend.alerts.refresh --states CT,NY
    python -m backend.alerts.refresh --skip-state
    python -m backend.alerts.refresh --congress 119

Default state set tracks the eids currently in `backend/data/ftm_eids.csv`
(CT, NY, NJ, CA, MA). Adjust as that CSV grows.
"""

import argparse
import asyncio
import sys
import traceback
from typing import Iterable

from .ingest_federal_votes import (
    DEFAULT_CONGRESS,
    DEFAULT_VOTE_LEAD_DAYS as FED_LEAD_DAYS,
    ingest_federal_votes,
)
from .ingest_state_votes import (
    DEFAULT_VOTE_LEAD_DAYS as STATE_LEAD_DAYS,
    ingest_state_votes,
)
from .pipeline import run_pipeline


DEFAULT_STATES = ("CT", "NY", "NJ", "CA", "MA")


def _run_federal(congress: int, lead_days: int) -> dict | None:
    """Run the federal ingester, swallowing errors so the pipeline still runs.

    Returns the stats dict on success, None on failure.
    """
    print(f"[refresh] === federal ingest (congress={congress}) ===")
    try:
        return asyncio.run(ingest_federal_votes(congress=congress, lead_days=lead_days))
    except Exception as e:
        print(f"[refresh] federal ingest FAILED: {e}")
        traceback.print_exc()
        return None


def _run_state(state: str, lead_days: int) -> dict | None:
    """Run the state ingester for one state, swallowing errors.

    Returns the stats dict on success, None on failure.
    """
    print(f"[refresh] === state ingest (state={state}) ===")
    try:
        return asyncio.run(ingest_state_votes(state=state, lead_days=lead_days))
    except Exception as e:
        print(f"[refresh] state ingest for {state} FAILED: {e}")
        traceback.print_exc()
        return None


def run(
    states: Iterable[str] = DEFAULT_STATES,
    congress: int = DEFAULT_CONGRESS,
    fed_lead_days: int = FED_LEAD_DAYS,
    state_lead_days: int = STATE_LEAD_DAYS,
    skip_federal: bool = False,
    skip_state: bool = False,
) -> dict:
    """Run the full refresh and return a roll-up summary."""
    summary = {
        "federal_stats": None,
        "state_stats": {},
        "ingest_failures": [],
        "pipeline_stats": None,
    }

    if not skip_federal:
        fed = _run_federal(congress=congress, lead_days=fed_lead_days)
        summary["federal_stats"] = fed
        if fed is None:
            summary["ingest_failures"].append("federal")
    else:
        print("[refresh] skipping federal ingest (--skip-federal)")

    if not skip_state:
        for state in states:
            state = state.strip().upper()
            if not state:
                continue
            stats = _run_state(state=state, lead_days=state_lead_days)
            summary["state_stats"][state] = stats
            if stats is None:
                summary["ingest_failures"].append(f"state:{state}")
    else:
        print("[refresh] skipping state ingest (--skip-state)")

    print("[refresh] === pipeline ===")
    summary["pipeline_stats"] = run_pipeline()

    print("[refresh] === summary ===")
    print(f"  federal: {summary['federal_stats']}")
    for st, st_stats in summary["state_stats"].items():
        print(f"  state[{st}]: {st_stats}")
    if summary["ingest_failures"]:
        print(f"  ingest_failures: {summary['ingest_failures']}")
    print(f"  pipeline: {summary['pipeline_stats']}")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--states",
        default=",".join(DEFAULT_STATES),
        help=f"Comma-separated state codes (default: {','.join(DEFAULT_STATES)})",
    )
    p.add_argument("--congress", type=int, default=DEFAULT_CONGRESS,
                   help=f"Congress number for federal ingest (default: {DEFAULT_CONGRESS})")
    p.add_argument("--fed-lead-days", type=int, default=FED_LEAD_DAYS,
                   help="Status->vote lead-day projection for federal bills")
    p.add_argument("--state-lead-days", type=int, default=STATE_LEAD_DAYS,
                   help="Engrossment->vote lead-day projection for state bills")
    p.add_argument("--skip-federal", action="store_true", help="Skip the federal ingest step")
    p.add_argument("--skip-state", action="store_true", help="Skip all state ingest steps")
    args = p.parse_args()

    states = [s for s in (x.strip() for x in args.states.split(",")) if s]

    try:
        run(
            states=states,
            congress=args.congress,
            fed_lead_days=args.fed_lead_days,
            state_lead_days=args.state_lead_days,
            skip_federal=args.skip_federal,
            skip_state=args.skip_state,
        )
    except Exception as e:
        print(f"[refresh] pipeline FAILED: {e}")
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
