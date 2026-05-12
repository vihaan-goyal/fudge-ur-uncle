"""End-to-end smoke test for the refresh orchestrator.

The component-level tests (`test_ingest_federal_votes.py`, `test_pipeline.py`)
already lock in each step's behavior. This file verifies the *chaining*:
    federal ingest → per-state ingest → pipeline
all run in one shot, hand off DB state to each other, and an alert lands.

Also covers the failure-isolation contract: if a state ingest raises, the
pipeline still runs and federal alerts still get produced. This is the
property that lets the orchestrator be safe to run on a cron — a flaky
upstream shouldn't poison the alert table.

Uses the same FUU_DB_PATH tmp-db trick as the other pipeline tests; project
root must be on sys.path because refresh.py uses `from .pipeline import ...`.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def clean_refresh_db(app):
    """Wipe pipeline tables so the refresh starts from a known-empty state."""
    from db import connect
    with connect() as conn:
        for tbl in ("alerts", "donations", "scheduled_votes",
                    "industry_baselines", "news_mentions", "ai_cache"):
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
    yield


def _seed_federal_donation(amount: float = 75_000, industry: str = "pharmaceuticals",
                           actor_id: str = "TEST_REP") -> int:
    """Insert a federal donation that should pair with a healthcare bill."""
    from db import connect
    today = date.today()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO donations
               (actor_type, actor_id, pac_name, industry, amount, donation_date, fec_filing_id)
               VALUES ('federal', ?, ?, ?, ?, ?, ?)""",
            (actor_id, "Test PAC", industry, amount,
             today - timedelta(days=2), f"TEST-REFRESH-{industry}"),
        )
        conn.commit()
        return cur.lastrowid


def _fed_bill(number, title, status_date, status="Reported by Committee", chamber="senate"):
    return {
        "bill_id": f"{number.lower().replace('.', '')}-119",
        "number": number,
        "title": title,
        "status": status,
        "status_date": status_date.isoformat() if isinstance(status_date, date) else status_date,
        "chamber": chamber,
        "congress": 119,
    }


def _state_bill(number, title, status_date, chamber="House"):
    """Shape one entry as `legiscan.get_active_bills` would return it."""
    return {
        "bill_id": int(number.replace("HB", "").replace("SB", "")) + 10000,
        "number": number,
        "title": title,
        "status": "engrossed",
        "status_date": status_date.isoformat() if isinstance(status_date, date) else status_date,
        "chamber": chamber,
    }


def test_refresh_chains_ingest_then_pipeline(clean_refresh_db):
    """Happy path: federal + one state ingest run, then pipeline scores the
    seeded donation against the freshly-ingested federal bill and writes an
    alert. Verifies both ingest legs land rows and the pipeline saw them."""
    from db import connect
    from backend.alerts import refresh

    today = date.today()
    fed_bills = [
        _fed_bill("S.872", "Prescription Drug Pricing Reform Act", today),  # healthcare
    ]
    state_bills = [
        _state_bill("HB1001", "Clean Air Standards Modernization Act", today),  # environment
    ]

    async def fake_fed(**_kw):
        return fed_bills

    async def fake_state(state):
        # Same payload regardless of state — the orchestrator iterates and
        # we just want to prove each call lands a row tagged with that state.
        return state_bills

    donation_id = _seed_federal_donation()

    async def _noop_index(*_a, **_kw):
        return {}

    with patch("api.congress_gov.get_active_bills", new=fake_fed), \
         patch("api.legiscan.get_active_bills", new=fake_state), \
         patch("api.legiscan.build_state_vote_index", new=_noop_index):
        summary = refresh.run(states=("CT", "NY"))

    # Federal ingest landed.
    assert summary["federal_stats"]["rows_inserted"] == 1
    # State ingest landed once per state.
    assert set(summary["state_stats"].keys()) == {"CT", "NY"}
    for st in ("CT", "NY"):
        assert summary["state_stats"][st]["rows_inserted"] == 1

    # Pipeline ran and produced an alert from the seeded federal donation.
    pl = summary["pipeline_stats"]
    assert pl is not None
    assert pl["alerts_written_new"] >= 1, pl

    with connect() as conn:
        fed_rows = conn.execute(
            "SELECT bill_number FROM scheduled_votes WHERE jurisdiction = 'federal'"
        ).fetchall()
        ct_rows = conn.execute(
            "SELECT bill_number FROM scheduled_votes WHERE jurisdiction = 'state' AND state_code = 'CT'"
        ).fetchall()
        ny_rows = conn.execute(
            "SELECT bill_number FROM scheduled_votes WHERE jurisdiction = 'state' AND state_code = 'NY'"
        ).fetchall()
        alerts = conn.execute(
            "SELECT id FROM alerts WHERE donation_id = ?", (donation_id,)
        ).fetchall()

    assert [r["bill_number"] for r in fed_rows] == ["S.872"]
    assert [r["bill_number"] for r in ct_rows] == ["HB1001"]
    assert [r["bill_number"] for r in ny_rows] == ["HB1001"]
    assert len(alerts) >= 1, "expected pipeline to produce at least one alert from the seeded pair"


def test_refresh_continues_when_state_ingest_raises(clean_refresh_db):
    """Failure isolation: a state-ingest crash must NOT block the pipeline.
    Critical for cron use — Legiscan blips shouldn't lose us federal alerts."""
    from db import connect
    from backend.alerts import refresh

    today = date.today()

    async def fake_fed(**_kw):
        return [_fed_bill("S.872", "Prescription Drug Pricing Reform Act", today)]

    async def fake_state_explodes(state):
        raise RuntimeError(f"simulated upstream wedge for {state}")

    _seed_federal_donation()

    async def _noop_index(*_a, **_kw):
        return {}

    with patch("api.congress_gov.get_active_bills", new=fake_fed), \
         patch("api.legiscan.get_active_bills", new=fake_state_explodes), \
         patch("api.legiscan.build_state_vote_index", new=_noop_index):
        summary = refresh.run(states=("CT",))

    assert summary["state_stats"]["CT"] is None
    assert summary["ingest_failures"] == ["state:CT"]
    # Pipeline still ran.
    assert summary["pipeline_stats"] is not None
    assert summary["pipeline_stats"]["alerts_written_new"] >= 1

    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]
    assert n >= 1, "federal alert should land even when state ingest crashed"


def test_refresh_main_returns_nonzero_when_pipeline_raises(clean_refresh_db):
    """The CLI exit code is the cron-friendly signal. Ingester hiccups are
    swallowed, but a pipeline crash must surface as non-zero so a scheduled
    job fires its alarm."""
    from backend.alerts import refresh

    async def fake_fed(**_kw):
        return []

    async def fake_state(state):
        return []

    def boom():
        raise RuntimeError("simulated pipeline crash")

    argv_backup = sys.argv[:]
    sys.argv = ["refresh", "--states", "CT", "--skip-state"]
    try:
        with patch("api.congress_gov.get_active_bills", new=fake_fed), \
             patch("backend.alerts.refresh.run_pipeline", new=boom):
            rc = refresh.main()
    finally:
        sys.argv = argv_backup

    assert rc == 1


def test_refresh_skip_flags_short_circuit_correctly(clean_refresh_db):
    """`--skip-federal` and `--skip-state` skip their leg without running it.
    Lets ops re-run just the pipeline (e.g. after a calibration tweak) without
    re-burning ingest quota."""
    from backend.alerts import refresh

    fed_called = {"n": 0}
    state_called = {"n": 0}

    async def fake_fed(**_kw):
        fed_called["n"] += 1
        return []

    async def fake_state(state):
        state_called["n"] += 1
        return []

    async def _noop_index(*_a, **_kw):
        return {}

    with patch("api.congress_gov.get_active_bills", new=fake_fed), \
         patch("api.legiscan.get_active_bills", new=fake_state), \
         patch("api.legiscan.build_state_vote_index", new=_noop_index):
        summary = refresh.run(states=("CT",), skip_federal=True, skip_state=True)

    assert fed_called["n"] == 0
    assert state_called["n"] == 0
    assert summary["federal_stats"] is None
    assert summary["state_stats"] == {}
    assert summary["pipeline_stats"] is not None
