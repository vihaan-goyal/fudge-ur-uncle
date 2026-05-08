"""Tests for the federal scheduled-vote ingester.

Two layers:
  1. `is_floor_imminent` — pure regex matcher. Lock in the patterns the
     ingester relies on so a future tweak to `_FLOOR_IMMINENT_PATTERN`
     doesn't silently drop "Reported by ..." or "Passed Senate".
  2. `ingest_federal_votes` — DB-write behavior. Stubs out
     `congress_gov.get_active_bills` so we never hit the live API; the
     fixture wipes scheduled_votes between tests so cases don't bleed.

Uses the same FUU_DB_PATH tmp-db trick as conftest.py + test_pipeline.py:
project root must be on sys.path so the ingester's package-relative
imports (`from ..db`) resolve.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------- matcher ----------

@pytest.mark.parametrize("text", [
    "Placed on Senate Legislative Calendar under General Orders.",
    "Placed on the Union Calendar, Calendar No. 142.",
    "Reported by Committee on Finance with amendments.",
    "Reported (Original) by the Committee on Energy.",
    "Reported favorably without amendment.",
    "Passed Senate without amendment by Unanimous Consent.",
    "Passed House by recorded vote.",
    "Passed Senate as amended.",
    "Received in the House.",
    "Received in the Senate.",
    "Motion to proceed to consideration of measure agreed to.",
    "Considered by the Senate.",
    "On agreeing to the resolution, the vote was 232 yeas to 198 nays.",
    "On agreeing to the amendment.",
    "Engrossed amendment as agreed to by the Senate.",
    "Discharge petition filed.",
    "Committee on Rules granted a closed rule.",
])
def test_is_floor_imminent_matches_expected(text):
    from api.congress_gov import is_floor_imminent
    assert is_floor_imminent(text), f"matcher should accept: {text!r}"


@pytest.mark.parametrize("text", [
    "",
    "Introduced in House.",
    "Referred to the Committee on the Judiciary.",
    "Sponsor introductory remarks on measure.",
    "Became Public Law No: 119-12.",
    "Presented to President.",
    "Signed by President.",
    "Held at the desk.",
    "Read twice.",
])
def test_is_floor_imminent_rejects_non_floor_text(text):
    from api.congress_gov import is_floor_imminent
    assert not is_floor_imminent(text), f"matcher should reject: {text!r}"


# ---------- ingester ----------

@pytest.fixture
def clean_federal_votes_db(app):
    """Wipe scheduled_votes + alerts so each ingester test starts fresh.
    Depends on `app` so the schema is initialized before we DELETE."""
    from db import connect
    with connect() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM scheduled_votes")
        conn.commit()
    yield


def _bill(number, title, status_date, status="Reported by Committee", chamber="senate"):
    """Shape one entry as `congress_gov.get_active_bills` would return it."""
    return {
        "bill_id": f"{number.lower().replace('.', '')}-119",
        "number": number,
        "title": title,
        "status": status,
        "status_date": status_date.isoformat() if isinstance(status_date, date) else status_date,
        "chamber": chamber,
        "congress": 119,
    }


def _fed_rows(conn):
    return conn.execute(
        """SELECT bill_number, title, category, scheduled_date, chamber
           FROM scheduled_votes
           WHERE jurisdiction = 'federal' AND state_code IS NULL
           ORDER BY bill_number"""
    ).fetchall()


def test_ingester_writes_categorized_bills_and_skips_uncategorized(clean_federal_votes_db):
    """Categorizable titles get rows; titles that match no keyword are dropped silently."""
    import asyncio
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    today = date.today()
    fake_bills = [
        _bill("S.1190", "Clean Air Standards Modernization Act", today),  # environment
        _bill("S.872", "Prescription Drug Pricing Reform Act", today),    # healthcare
        # Pure naming/commemoration — matches no category keyword. Note that
        # "bridge" / "transportation" would land in `infrastructure`, so don't
        # use those even in a "renaming" title.
        _bill("H.R.999", "Designating the Federal Office Building in Smithville", today),
    ]

    async def fake_get_active_bills(**_kw):
        return fake_bills

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills):
        stats = asyncio.run(ingest_federal_votes())

    assert stats["bills_considered"] == 3
    assert stats["rows_inserted"] == 2
    assert stats["uncategorized_skipped"] == 1

    with connect() as conn:
        rows = _fed_rows(conn)
    assert [r["bill_number"] for r in rows] == ["S.1190", "S.872"]
    assert {r["category"] for r in rows} == {"environment", "healthcare"}


def test_ingester_purges_stale_rows_when_new_keepers_arrive(clean_federal_votes_db):
    """A bill that was categorized in a prior run but no longer appears in the
    active list should be deleted, along with any dependent alerts."""
    import asyncio
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    today = date.today()

    # Pre-seed a stale federal row (simulates a bill that fell off the active list).
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_votes
               (jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber)
               VALUES ('federal', NULL, 'S.OLD', 'Old Bill', 'environment', ?, 'senate')""",
            (today,),
        )
        old_vote_id = cur.lastrowid
        cur = conn.execute(
            """INSERT INTO donations
               (actor_type, actor_id, pac_name, industry, amount, donation_date)
               VALUES ('federal', 'X001', 'Test PAC', 'oil_gas', 5000, ?)""",
            (today - timedelta(days=2),),
        )
        donation_id = cur.lastrowid
        conn.execute(
            """INSERT INTO alerts
               (actor_type, actor_id, donation_id, vote_id, score, urgent, headline, body, signals_json)
               VALUES ('federal', 'X001', ?, ?, 0.5, 0, 'h', 'b', '{}')""",
            (donation_id, old_vote_id),
        )
        conn.commit()

    async def fake_get_active_bills(**_kw):
        return [_bill("S.NEW", "Renewable Energy Tax Credit Extension", today)]

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills):
        stats = asyncio.run(ingest_federal_votes())

    assert stats["rows_inserted"] == 1
    assert stats["rows_purged"] == 1, stats
    assert stats["alerts_purged"] == 1, stats

    with connect() as conn:
        rows = _fed_rows(conn)
        assert [r["bill_number"] for r in rows] == ["S.NEW"]
        # Dependent alert was cleaned up too.
        n = conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]
        assert n == 0


def test_ingester_does_not_purge_when_no_keepers(clean_federal_votes_db):
    """Safety: an upstream wedge that returns 0 floor-imminent bills, or one
    where every result is uncategorized, must not nuke the existing table.
    Without this guard, a transient API blip would wipe all federal votes."""
    import asyncio
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    today = date.today()

    with connect() as conn:
        conn.execute(
            """INSERT INTO scheduled_votes
               (jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber)
               VALUES ('federal', NULL, 'S.KEEP', 'Keep Me', 'environment', ?, 'senate')""",
            (today,),
        )
        conn.commit()

    # Every bill in the live response is uncategorized -> keepers stays empty.
    async def fake_get_active_bills(**_kw):
        return [_bill("H.R.1", "Procedural Renaming Act", today)]

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills):
        stats = asyncio.run(ingest_federal_votes())

    assert stats["rows_purged"] == 0
    assert stats["uncategorized_skipped"] == 1

    with connect() as conn:
        rows = _fed_rows(conn)
    assert [r["bill_number"] for r in rows] == ["S.KEEP"], (
        "pre-existing row was wiped despite empty keepers — safety guard is broken"
    )


def test_ingester_bumps_stalled_status_date_to_today(clean_federal_votes_db):
    """A bill engrossed 100 days ago is still pending business; its
    status_date+14 projection lands well in the past. The ingester should
    bump scheduled_date to today so V (vote-proximity) doesn't collapse."""
    import asyncio
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    today = date.today()
    stale_status_date = today - timedelta(days=100)

    async def fake_get_active_bills(**_kw):
        return [_bill("S.STALE", "Clean Energy Modernization Act", stale_status_date)]

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills):
        asyncio.run(ingest_federal_votes())

    with connect() as conn:
        row = conn.execute(
            """SELECT scheduled_date FROM scheduled_votes
               WHERE bill_number = 'S.STALE'"""
        ).fetchone()

    sched = row["scheduled_date"]
    if isinstance(sched, str):
        sched = date.fromisoformat(sched)
    assert sched == today, (
        f"expected stale bill bumped to today ({today}); got {sched}"
    )
