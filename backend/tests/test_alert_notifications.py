"""Urgent-alert email notification pass.

Locks in:
  - state + issue matching (right rep state, right user issues)
  - email_verified / notify_alerts / email_bouncing gating
  - dedupe via alert_email_sends so re-running doesn't double-send
  - graceful behavior when send_email reports failure (still records send)
"""
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def clean_db(app):
    """Wipe everything that this test touches so ordering doesn't matter."""
    from db import connect
    with connect() as conn:
        for tbl in ("alert_email_sends", "alerts", "donations",
                    "scheduled_votes", "users", "sessions",
                    "email_verifications", "password_resets"):
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
    yield


@pytest.fixture
def captured_emails(monkeypatch):
    """Patch send_email at the import site used inside alert_notifications."""
    captured: list[tuple[str, str, str, str]] = []

    async def _fake_send(*, to, subject, html, text):
        captured.append((to, subject, html, text))
        return True

    monkeypatch.setattr("api.alert_notifications.send_email", _fake_send)
    return captured


@pytest.fixture
def fake_legislators(monkeypatch):
    """Pin the legislator cache so we don't hit GitHub."""
    fake = [
        {
            "id": {"bioguide": "M001169"},
            "name": {"official_full": "Christopher Murphy", "first": "Chris", "last": "Murphy"},
            "terms": [{"state": "CT", "type": "sen"}],
        },
        {
            "id": {"bioguide": "B001277"},
            "name": {"official_full": "Richard Blumenthal", "first": "Richard", "last": "Blumenthal"},
            "terms": [{"state": "CT", "type": "sen"}],
        },
        {
            "id": {"bioguide": "S000033"},
            "name": {"official_full": "Bernie Sanders", "first": "Bernie", "last": "Sanders"},
            "terms": [{"state": "VT", "type": "sen"}],
        },
    ]

    async def _fake_fetch(use_cache: bool = True):
        return fake

    monkeypatch.setattr("api.alert_notifications.legislators.fetch_legislators", _fake_fetch)
    return fake


def _make_user(conn, *, state="CT", issues=None, notify=True, verified=True, bouncing=False):
    email = f"alertuser-{uuid.uuid4().hex[:8]}@test.local"
    cur = conn.execute(
        """INSERT INTO users (email, password_hash, name, state, issues,
                              email_verified, notify_alerts, email_bouncing)
           VALUES (?, 'x', 'Alice', ?, ?, ?, ?, ?)""",
        (email, state, json.dumps(issues or []), 1 if verified else 0,
         1 if notify else 0, 1 if bouncing else 0),
    )
    return cur.lastrowid, email


def _make_urgent_alert(
    conn, *, actor_type="federal", actor_id="M001169",
    category="healthcare", state_code=None, days_until=3,
    bill_number="S.872",
):
    """Insert a donation + scheduled_vote + alert(urgent=1) triple. Returns
    alert_id so the caller can assert on alert_email_sends."""
    today = date.today()
    cur = conn.execute(
        """INSERT INTO donations (actor_type, actor_id, pac_name, industry,
                                  amount, donation_date, fec_filing_id)
           VALUES (?, ?, 'Pharma PAC', 'pharmaceuticals', 75000, ?, ?)""",
        (actor_type, actor_id, today - timedelta(days=2),
         f"DON-{actor_id}-{bill_number}"),
    )
    donation_id = cur.lastrowid
    jurisdiction = "federal" if actor_type == "federal" else "state"
    cur = conn.execute(
        """INSERT INTO scheduled_votes (jurisdiction, state_code, bill_number,
                                        title, category, scheduled_date, chamber)
           VALUES (?, ?, ?, 'Test Bill', ?, ?, 'Senate')""",
        (jurisdiction, state_code, bill_number, category,
         today + timedelta(days=days_until)),
    )
    vote_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO alerts (actor_type, actor_id, donation_id, vote_id,
                               score, urgent, headline, body, signals_json,
                               updated_at)
           VALUES (?, ?, ?, ?, 0.78, 1, 'Urgent test', 'body', '{}',
                   CURRENT_TIMESTAMP)""",
        (actor_type, actor_id, donation_id, vote_id),
    )
    return cur.lastrowid


# ---------- core matching ----------

def test_sends_to_matching_user_and_records_dedupe(clean_db, captured_emails, fake_legislators):
    """Matching user (CT + healthcare in issues) gets one email; ledger row
    inserted; second call sends nothing."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        uid, email = _make_user(conn, state="CT", issues=["healthcare"])
        alert_id = _make_urgent_alert(conn)

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 1
    assert len(captured_emails) == 1
    assert captured_emails[0][0] == email
    assert "Murphy" in captured_emails[0][1]  # rep name in subject

    with connect() as conn:
        ledger = conn.execute(
            "SELECT delivered FROM alert_email_sends WHERE alert_id = ? AND user_id = ?",
            (alert_id, uid),
        ).fetchone()
    assert ledger is not None and ledger["delivered"] == 1

    # Second run is a no-op.
    captured_emails.clear()
    stats2 = asyncio.run(notify_pending_urgent_alerts())
    assert stats2["emails_sent"] == 0
    assert captured_emails == []


def test_skips_user_in_different_state(clean_db, captured_emails, fake_legislators):
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        # Rep is CT (Murphy); user is NY — no match.
        _make_user(conn, state="NY", issues=["healthcare"])
        _make_urgent_alert(conn, actor_id="M001169")

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0
    assert captured_emails == []


def test_skips_user_without_matching_issue(clean_db, captured_emails, fake_legislators):
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["environment"])
        _make_urgent_alert(conn, category="healthcare")

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0


def test_skips_unverified_user(clean_db, captured_emails, fake_legislators):
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["healthcare"], verified=False)
        _make_urgent_alert(conn)

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0


def test_skips_user_with_notify_off(clean_db, captured_emails, fake_legislators):
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["healthcare"], notify=False)
        _make_urgent_alert(conn)

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0


def test_skips_bouncing_user(clean_db, captured_emails, fake_legislators):
    """Latched flag — bouncing addresses don't receive even with notify_alerts=1."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["healthcare"], bouncing=True)
        _make_urgent_alert(conn)

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0


def test_state_alert_matches_state_code(clean_db, captured_emails, fake_legislators):
    """State alerts route by scheduled_votes.state_code (not bioguide lookup)."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        uid_ct, email_ct = _make_user(conn, state="CT", issues=["environment"])
        uid_ny, _ = _make_user(conn, state="NY", issues=["environment"])
        _make_urgent_alert(
            conn, actor_type="state", actor_id="9001",
            category="environment", state_code="CT", bill_number="SB00100",
        )

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 1
    assert captured_emails[0][0] == email_ct


def test_failed_send_still_records_with_delivered_zero(clean_db, monkeypatch, fake_legislators):
    """Failed send leaves a delivered=0 row so the next run doesn't retry forever."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    async def _fail_send(**_kw):
        return False
    monkeypatch.setattr("api.alert_notifications.send_email", _fail_send)

    with connect() as conn:
        uid, _ = _make_user(conn, state="CT", issues=["healthcare"])
        alert_id = _make_urgent_alert(conn)

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_failed"] == 1
    assert stats["emails_sent"] == 0
    with connect() as conn:
        row = conn.execute(
            "SELECT delivered FROM alert_email_sends WHERE alert_id = ? AND user_id = ?",
            (alert_id, uid),
        ).fetchone()
    assert row is not None and row["delivered"] == 0


def test_dismissed_alerts_skipped(clean_db, captured_emails, fake_legislators):
    """An urgent alert the user dismissed in the UI must not generate email."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["healthcare"])
        alert_id = _make_urgent_alert(conn)
        conn.execute("UPDATE alerts SET dismissed = 1 WHERE id = ?", (alert_id,))

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0


def test_non_urgent_alerts_skipped(clean_db, captured_emails, fake_legislators):
    """Only urgent=1 rows trigger email — regular alerts stay in-app only."""
    from db import connect
    from api.alert_notifications import notify_pending_urgent_alerts
    import asyncio

    with connect() as conn:
        _make_user(conn, state="CT", issues=["healthcare"])
        alert_id = _make_urgent_alert(conn)
        conn.execute("UPDATE alerts SET urgent = 0 WHERE id = ?", (alert_id,))

    stats = asyncio.run(notify_pending_urgent_alerts())
    assert stats["emails_sent"] == 0
