"""End-to-end pipeline test: seed a donation + scheduled vote, run the
pipeline, assert an alert lands with the expected shape.

Locks in the calibration knobs (PROXY_DONATION_R, NO_BASELINE_A_HONEST), the
score formula, and the stale-sweep behavior. Symptoms of regression:
  - score drift past the alert threshold means a known-good case stops alerting
  - state-side calibration accidentally re-enabled for federal -> federal
    scores collapse
  - the sweep deletes a row it shouldn't (or fails to delete one it should)

Uses the same FUU_DB_PATH tmp-db trick as conftest.py so it doesn't clobber
dev data. The pipeline module uses package-relative imports (`from ..db`),
so we need the project root on sys.path — not just `backend/`.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _seed_pair(conn, *, donation_amount: float, days_until_vote: int,
               actor_id: str = "TEST_REP", actor_type: str = "federal",
               jurisdiction: str = "federal", state_code=None,
               industry: str = "oil_gas", category: str = "environment"):
    """Insert a single (donation, scheduled_vote) pair and return their IDs."""
    today = date.today()
    cur = conn.execute(
        """INSERT INTO donations
           (actor_type, actor_id, pac_name, industry, amount, donation_date, fec_filing_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (actor_type, actor_id, "Test PAC", industry, donation_amount,
         today - timedelta(days=2), f"TEST-{actor_id}-{industry}"),
    )
    donation_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO scheduled_votes
           (jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (jurisdiction, state_code, f"TEST.{actor_id}", "Test Bill", category,
         today + timedelta(days=days_until_vote), "senate"),
    )
    vote_id = cur.lastrowid
    conn.commit()
    return donation_id, vote_id


def _alert_count(conn, actor_id: str = "TEST_REP") -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM alerts WHERE actor_id = ?", (actor_id,)
    ).fetchone()["n"]


@pytest.fixture
def clean_pipeline_db(app):
    """Wipe pipeline tables between tests so cases don't bleed into each other.
    Depends on `app` so the schema is initialized before we DELETE.
    Sessions/users from auth tests are left alone."""
    from db import connect
    with connect() as conn:
        for tbl in ("alerts", "donations", "scheduled_votes",
                    "industry_baselines", "news_mentions", "ai_cache"):
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
    yield


def test_federal_alert_fires_on_known_good_case(clean_pipeline_db):
    """A $75k oil donation 2 days before a climate vote should clear the alert
    threshold under default scoring (T=1, V≈0.87, D≈0.96, R≈0.94, A=0.5,
    score ≈ 0.71 → urgent)."""
    from db import connect
    from backend.alerts.pipeline import run_pipeline

    with connect() as conn:
        _seed_pair(conn, donation_amount=75_000, days_until_vote=2)

    stats = run_pipeline()
    assert stats["alerts_written_new"] >= 1, stats

    with connect() as conn:
        row = conn.execute(
            """SELECT score, urgent, headline FROM alerts
               WHERE actor_id = 'TEST_REP'"""
        ).fetchone()
    assert row is not None
    assert row["score"] > 0.6, f"expected urgent (score>0.6), got {row['score']}"
    assert row["urgent"] == 1
    # Headline should mention the dollar amount and category
    assert "75,000" in row["headline"]
    assert "environment" in row["headline"]


def test_state_calibration_lowers_score(clean_pipeline_db):
    """Same $45k donation x state vote should land alert-but-not-urgent under
    state calibration (proxy_r=0.4, no_baseline_a=0.0). Pre-calibration this
    case scored 0.86 urgent; post-calibration it should be in [0.3, 0.6]."""
    from db import connect
    from backend.alerts.pipeline import run_pipeline

    with connect() as conn:
        _seed_pair(
            conn, donation_amount=45_000, days_until_vote=3,
            actor_id="STATE_REP_X", actor_type="state",
            jurisdiction="state", state_code="CT",
            industry="public_sector_unions", category="education",
        )
        # Mark the actor as belonging to CT via the cached-roster mechanism the
        # state-side pipeline reads from.
        import json
        conn.execute(
            "INSERT INTO ai_cache (cache_key, value_json, expires_at) VALUES (?, ?, ?)",
            ("legiscan:people:CT",
             json.dumps([{"people_id": "STATE_REP_X", "state": "CT", "name": "Test"}]),
             (datetime.now() + timedelta(days=1)).isoformat()),
        )
        conn.commit()

    stats = run_pipeline()
    assert stats["alerts_written_new"] >= 1, stats

    with connect() as conn:
        row = conn.execute(
            "SELECT score, urgent FROM alerts WHERE actor_id = 'STATE_REP_X'"
        ).fetchone()
    assert row is not None
    assert 0.3 < row["score"] < 0.6, (
        f"state $45k case should be alert-but-not-urgent under calibration; "
        f"got score={row['score']}"
    )
    assert row["urgent"] == 0


def test_stale_alert_swept_when_donation_ages_out(clean_pipeline_db):
    """An alert written under a fresh donation should be removed by the
    stale-sweep when the donation's date moves outside the lookback window."""
    from db import connect
    from backend.alerts.pipeline import run_pipeline

    with connect() as conn:
        d_id, _ = _seed_pair(conn, donation_amount=75_000, days_until_vote=2)

    run_pipeline()
    with connect() as conn:
        assert _alert_count(conn) == 1

    # Push the donation 400 days into the past — outside the 180-day window.
    with connect() as conn:
        conn.execute(
            "UPDATE donations SET donation_date = ? WHERE id = ?",
            ((date.today() - timedelta(days=400)).isoformat(), d_id),
        )
        conn.commit()

    stats = run_pipeline()
    assert stats["alerts_swept_stale"] >= 1, stats

    with connect() as conn:
        assert _alert_count(conn) == 0, "stale alert was not swept"
