"""Email verification + password reset.

Patches `api.email_sender.send_email` so the tests don't make real network
calls — and captures every outbound message so we can assert link contents.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _new_email() -> str:
    return f"emailflow-{uuid.uuid4().hex[:8]}@test.local"


@pytest.fixture
def captured_emails(monkeypatch):
    """List of (to, subject, html, text) tuples, in send order."""
    captured: list[tuple[str, str, str, str]] = []

    async def _fake_send(*, to, subject, html, text):
        captured.append((to, subject, html, text))
        return True

    # Patch the symbol auth.py imported — patching the source module isn't
    # enough since `from ... import send_email` already bound a reference.
    monkeypatch.setattr("api.auth.send_email", _fake_send)
    return captured


@pytest.fixture(autouse=True)
def _reset_throttles():
    from api.auth import _login_throttle_reset_all, _email_throttle_reset_all
    _login_throttle_reset_all()
    _email_throttle_reset_all()
    yield
    _login_throttle_reset_all()
    _email_throttle_reset_all()


def _extract_verify_token(text: str) -> str:
    m = re.search(r"\?verify=([^\s]+)", text)
    assert m, f"no verify token in: {text!r}"
    return m.group(1)


def _extract_reset_token(text: str) -> str:
    m = re.search(r"\?reset=([^\s]+)", text)
    assert m, f"no reset token in: {text!r}"
    return m.group(1)


def _signup(client, email=None, password="correct horse battery staple"):
    email = email or _new_email()
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "name": "Alice", "state": "CT",
    })
    assert r.status_code == 200, r.text
    return email, password, r.json()


# ---------- Verification ----------

def test_signup_sends_verification_email(client, captured_emails):
    email, _, body = _signup(client)
    assert len(captured_emails) == 1
    to, subject, _, text = captured_emails[0]
    assert to == email
    assert "verify" in subject.lower()
    assert _extract_verify_token(text)
    assert body["user"]["email_verified"] is False


def test_verify_email_marks_user_verified(client, captured_emails):
    email, _, body = _signup(client)
    token = _extract_verify_token(captured_emails[0][3])

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is True

    # /me confirms the persisted flag
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert r.json()["user"]["email_verified"] is True


def test_verify_email_rejects_unknown_token(client, captured_emails):
    r = client.post("/api/auth/verify-email", json={"token": "this-is-not-a-real-token-x" * 2})
    assert r.status_code == 400


def test_verify_email_rejects_reused_token(client, captured_emails):
    _, _, _ = _signup(client)
    token = _extract_verify_token(captured_emails[0][3])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    # Second redemption fails — one-shot semantic.
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400


def test_verify_email_rejects_expired_token(client, captured_emails):
    """Expire the row directly so we don't have to wait 24h."""
    from db import connect

    _, _, _ = _signup(client)
    token = _extract_verify_token(captured_emails[0][3])
    expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    with connect() as conn:
        conn.execute(
            "UPDATE email_verifications SET expires_at = ? WHERE token = ?",
            (expired, token),
        )
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 400


def test_resend_verification_issues_fresh_token(client, captured_emails):
    _, _, body = _signup(client)
    headers = {"Authorization": f"Bearer {body['token']}"}
    original_token = _extract_verify_token(captured_emails[0][3])

    r = client.post("/api/auth/resend-verification", headers=headers)
    assert r.status_code == 200, r.text
    assert len(captured_emails) == 2
    new_token = _extract_verify_token(captured_emails[1][3])
    assert new_token != original_token

    # Old token is dead, new one works.
    assert client.post("/api/auth/verify-email", json={"token": original_token}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": new_token}).status_code == 200


def test_resend_verification_no_op_when_already_verified(client, captured_emails):
    _, _, body = _signup(client)
    headers = {"Authorization": f"Bearer {body['token']}"}
    token = _extract_verify_token(captured_emails[0][3])
    client.post("/api/auth/verify-email", json={"token": token})

    r = client.post("/api/auth/resend-verification", headers=headers)
    assert r.status_code == 200
    assert r.json().get("already_verified") is True
    # No new email sent — only the signup one in the captured list.
    assert len(captured_emails) == 1


def test_resend_verification_throttled(client, captured_emails):
    from api.auth import EMAIL_THROTTLE_MAX

    _, _, body = _signup(client)
    headers = {"Authorization": f"Bearer {body['token']}"}

    # Signup doesn't touch this throttle bucket. EMAIL_THROTTLE_MAX requests
    # are all allowed; the next one trips the limit.
    for _ in range(EMAIL_THROTTLE_MAX):
        ok = client.post("/api/auth/resend-verification", headers=headers)
        assert ok.status_code == 200, ok.text
    last = client.post("/api/auth/resend-verification", headers=headers)
    assert last.status_code == 429, last.text


def test_resend_verification_requires_auth(client):
    r = client.post("/api/auth/resend-verification")
    assert r.status_code == 401


# ---------- Forgot password ----------

def test_forgot_password_for_known_email_sends_link(client, captured_emails):
    email, _, _ = _signup(client)
    captured_emails.clear()

    r = client.post("/api/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert len(captured_emails) == 1
    to, subject, _, text = captured_emails[0]
    assert to == email
    assert "reset" in subject.lower()
    assert _extract_reset_token(text)


def test_forgot_password_silent_on_unknown_email(client, captured_emails):
    """No-enumeration guarantee: response identical, no email sent."""
    r = client.post("/api/auth/forgot-password", json={"email": "no-such-user@test.local"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert captured_emails == []


def test_forgot_password_silent_on_invalid_email(client, captured_emails):
    r = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert r.status_code == 200
    assert captured_emails == []


# ---------- Reset password ----------

def test_reset_password_changes_credential(client, captured_emails):
    email, original_password, _ = _signup(client)
    captured_emails.clear()

    client.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(captured_emails[0][3])

    new_password = "another sturdy passphrase here"
    r = client.post("/api/auth/reset-password", json={
        "token": token, "password": new_password,
    })
    assert r.status_code == 200, r.text

    # Old password fails, new one works.
    assert client.post("/api/auth/login", json={
        "email": email, "password": original_password,
    }).status_code == 401
    assert client.post("/api/auth/login", json={
        "email": email, "password": new_password,
    }).status_code == 200


def test_reset_password_invalidates_existing_sessions(client, captured_emails):
    """Password change kicks all other devices — the existing bearer token
    issued at signup must stop working after a reset."""
    email, _, body = _signup(client)
    captured_emails.clear()

    client.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(captured_emails[0][3])
    client.post("/api/auth/reset-password", json={
        "token": token, "password": "another sturdy passphrase here",
    })

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert r.status_code == 401, "signup-era session should have been invalidated"


def test_reset_password_rejects_unknown_token(client):
    r = client.post("/api/auth/reset-password", json={
        "token": "this-is-not-a-valid-token-xx",
        "password": "another sturdy passphrase here",
    })
    assert r.status_code == 400


def test_reset_password_rejects_reused_token(client, captured_emails):
    email, _, _ = _signup(client)
    captured_emails.clear()

    client.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(captured_emails[0][3])
    new_password = "first replacement passphrase"
    assert client.post("/api/auth/reset-password", json={
        "token": token, "password": new_password,
    }).status_code == 200
    # Token is now consumed.
    assert client.post("/api/auth/reset-password", json={
        "token": token, "password": "second replacement passphrase",
    }).status_code == 400


def test_reset_password_rejects_expired_token(client, captured_emails):
    from db import connect

    email, _, _ = _signup(client)
    captured_emails.clear()
    client.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(captured_emails[0][3])

    expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    with connect() as conn:
        conn.execute(
            "UPDATE password_resets SET expires_at = ? WHERE token = ?",
            (expired, token),
        )
    r = client.post("/api/auth/reset-password", json={
        "token": token, "password": "another sturdy passphrase here",
    })
    assert r.status_code == 400


def test_reset_password_rejects_weak_password(client, captured_emails):
    email, _, _ = _signup(client)
    captured_emails.clear()
    client.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(captured_emails[0][3])

    r = client.post("/api/auth/reset-password", json={
        "token": token, "password": "password123",
    })
    assert r.status_code == 400
    assert "common" in r.json()["detail"].lower()
