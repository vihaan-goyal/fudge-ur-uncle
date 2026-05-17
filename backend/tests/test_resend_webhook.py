"""POST /api/webhooks/resend.

Locks in the signature verification + the bounce/complaint side-effect on
users.notify_alerts / email_bouncing. We exercise the real endpoint via the
TestClient — the signature math is the part most likely to break in a
silent way if someone edits _verify_signature.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest


WEBHOOK_SECRET_PLAINTEXT = "test-webhook-secret-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _set_webhook_secret(monkeypatch):
    """Encode the plaintext secret as Resend would (base64 with whsec_ prefix)
    and patch config so the endpoint can verify our signed requests."""
    encoded = base64.b64encode(WEBHOOK_SECRET_PLAINTEXT.encode()).decode().rstrip("=")
    monkeypatch.setattr("config.RESEND_WEBHOOK_SECRET", f"whsec_{encoded}")
    # The webhook module imports config and reads .RESEND_WEBHOOK_SECRET each
    # request, so patching `config` is enough — no need to reach inside.
    yield


def _sign(body: bytes, message_id: str, timestamp: str, secret_plain: str = WEBHOOK_SECRET_PLAINTEXT) -> str:
    signed = f"{message_id}.{timestamp}.".encode() + body
    sig = base64.b64encode(
        hmac.new(secret_plain.encode(), signed, hashlib.sha256).digest()
    ).decode()
    return f"v1,{sig}"


def _post(client, payload: dict, *, header_overrides: dict | None = None):
    body = json.dumps(payload).encode()
    message_id = f"msg_{uuid.uuid4().hex}"
    timestamp = str(int(time.time()))
    headers = {
        "webhook-id": message_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": _sign(body, message_id, timestamp),
        "content-type": "application/json",
    }
    if header_overrides:
        headers.update(header_overrides)
    return client.post("/api/webhooks/resend", content=body, headers=headers)


def _create_user(client, email: str) -> int:
    """Sign up via the real flow so the row has notify_alerts/email_bouncing
    defaults from the schema, not whatever we'd hand-pick."""
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "correct horse battery staple",
        "name": "Bouncy Bill", "state": "CT",
    })
    assert r.status_code == 200, r.text
    return r.json()["user"]["id"]


# ---------- happy path ----------

def test_bounce_disables_notifications(client):
    email = f"bounce-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_user(client, email)

    r = _post(client, {
        "type": "email.bounced",
        "data": {"to": [email], "email_id": "e_x"},
    })
    assert r.status_code == 200, r.text
    assert r.json()["disabled"] == 1

    from db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT notify_alerts, email_bouncing FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    assert row["notify_alerts"] == 0
    assert row["email_bouncing"] == 1


def test_complaint_disables_notifications(client):
    email = f"spam-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_user(client, email)

    r = _post(client, {
        "type": "email.complained",
        "data": {"to": [email]},
    })
    assert r.status_code == 200, r.text

    from db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT notify_alerts, email_bouncing FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    assert row["notify_alerts"] == 0
    assert row["email_bouncing"] == 1


def test_unknown_event_acknowledged_no_op(client):
    """Resend retries on non-200 — we must return 200 for events we don't
    care about, but not touch any state."""
    email = f"open-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_user(client, email)

    r = _post(client, {
        "type": "email.opened",
        "data": {"to": [email]},
    })
    assert r.status_code == 200
    assert r.json()["ignored"] is True

    from db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT notify_alerts, email_bouncing FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    # Still defaults — opens shouldn't flip anything.
    assert row["notify_alerts"] == 1
    assert row["email_bouncing"] == 0


# ---------- signature failures ----------

def test_rejects_invalid_signature(client):
    body = json.dumps({"type": "email.bounced", "data": {"to": ["x@x.com"]}}).encode()
    message_id = "msg_xxx"
    timestamp = str(int(time.time()))
    headers = {
        "webhook-id": message_id,
        "webhook-timestamp": timestamp,
        # Wrong signature
        "webhook-signature": "v1,YWJjZGVmZ2hpams=",
        "content-type": "application/json",
    }
    r = client.post("/api/webhooks/resend", content=body, headers=headers)
    assert r.status_code == 401


def test_rejects_missing_headers(client):
    body = json.dumps({"type": "email.bounced", "data": {"to": ["x@x.com"]}}).encode()
    r = client.post("/api/webhooks/resend", content=body)
    assert r.status_code == 400


def test_rejects_stale_timestamp(client):
    """Replay protection — timestamp >5min old must fail before sig check."""
    email = f"stale-{uuid.uuid4().hex[:8]}@test.local"
    _create_user(client, email)

    body = json.dumps({"type": "email.bounced", "data": {"to": [email]}}).encode()
    message_id = f"msg_{uuid.uuid4().hex}"
    stale_ts = str(int(time.time()) - 60 * 60)  # 1 hour old
    headers = {
        "webhook-id": message_id,
        "webhook-timestamp": stale_ts,
        "webhook-signature": _sign(body, message_id, stale_ts),
        "content-type": "application/json",
    }
    r = client.post("/api/webhooks/resend", content=body, headers=headers)
    assert r.status_code == 400


def test_returns_503_when_secret_unset(client, monkeypatch):
    """Fail closed — without a configured secret we have no way to verify
    signatures, so every request must be rejected (with a retry-friendly 503)."""
    monkeypatch.setattr("config.RESEND_WEBHOOK_SECRET", "")
    r = _post(client, {"type": "email.bounced", "data": {"to": ["x@y.com"]}})
    assert r.status_code == 503


# ---------- edge cases ----------

def test_bounce_for_unknown_email_is_noop_200(client):
    """If we never had that account, the webhook should still 200 (so Resend
    stops retrying) but no row gets flipped."""
    r = _post(client, {
        "type": "email.bounced",
        "data": {"to": ["nobody-here@test.local"]},
    })
    assert r.status_code == 200
    assert r.json()["disabled"] == 0


def test_bounce_with_string_recipient(client):
    """Some Resend payloads put `to` as a plain string instead of a list."""
    email = f"str-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_user(client, email)

    r = _post(client, {
        "type": "email.bounced",
        "data": {"to": email},
    })
    assert r.status_code == 200
    assert r.json()["disabled"] == 1

    from db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT email_bouncing FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    assert row["email_bouncing"] == 1


def test_alternate_svix_header_names_accepted(client):
    """Resend currently sends `webhook-*`; older Svix infra uses `svix-*`.
    Either should verify successfully."""
    email = f"svix-{uuid.uuid4().hex[:8]}@test.local"
    _create_user(client, email)

    body = json.dumps({"type": "email.bounced", "data": {"to": [email]}}).encode()
    message_id = f"msg_{uuid.uuid4().hex}"
    timestamp = str(int(time.time()))
    headers = {
        "svix-id": message_id,
        "svix-timestamp": timestamp,
        "svix-signature": _sign(body, message_id, timestamp),
        "content-type": "application/json",
    }
    r = client.post("/api/webhooks/resend", content=body, headers=headers)
    assert r.status_code == 200, r.text
