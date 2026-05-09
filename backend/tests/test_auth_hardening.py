"""Regression tests for the auth-hardening pass.

Locks in five behaviors that don't exist in the smoke suite:

1. Common-password and email-as-password rejection at signup.
2. Login throttle: after N failed attempts on the same email, return 429.
3. Successful login clears the throttle counter for that key.
4. DELETE /me requires the current password (stolen-token mitigation).
5. _new_session opportunistically prunes expired session rows.
"""
import uuid

import pytest


def _new_email() -> str:
    return f"harden-{uuid.uuid4().hex[:8]}@test.local"


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Clear the in-process throttle between tests so ordering is irrelevant."""
    from api.auth import _login_throttle_reset_all
    _login_throttle_reset_all()
    yield
    _login_throttle_reset_all()


# ---------- 1. Password strength on signup ----------

@pytest.mark.parametrize("weak", [
    "password123",   # in common list
    "qwerty123",     # in common list
    "12345678",      # numeric, in common list
    "letmein123",    # common phrase
])
def test_signup_rejects_common_passwords(client, weak):
    r = client.post("/api/auth/signup", json={
        "email": _new_email(), "password": weak, "name": "X", "state": "CT",
    })
    assert r.status_code == 400, r.text
    assert "common" in r.json()["detail"].lower()


def test_signup_rejects_password_equal_to_email(client):
    email = _new_email()
    local = email.split("@", 1)[0]
    r = client.post("/api/auth/signup", json={
        "email": email, "password": local, "name": "X", "state": "CT",
    })
    assert r.status_code == 400, r.text
    assert "email" in r.json()["detail"].lower()


def test_signup_accepts_strong_password(client):
    r = client.post("/api/auth/signup", json={
        "email": _new_email(),
        "password": "correct horse battery staple",
        "name": "X", "state": "CT",
    })
    assert r.status_code == 200, r.text


# ---------- 2 & 3. Login throttle ----------

def test_login_throttle_locks_after_repeated_failures(client):
    from api.auth import LOGIN_MAX_FAILURES

    email = _new_email()
    client.post("/api/auth/signup", json={
        "email": email, "password": "correct horse battery staple",
        "name": "X", "state": "CT",
    })

    # LOGIN_MAX_FAILURES wrong attempts must each return 401.
    for _ in range(LOGIN_MAX_FAILURES):
        r = client.post("/api/auth/login", json={"email": email, "password": "wrongwrong"})
        assert r.status_code == 401, r.text

    # The next attempt — even with the right password — must be locked.
    r = client.post("/api/auth/login", json={
        "email": email, "password": "correct horse battery staple",
    })
    assert r.status_code == 429, r.text
    assert "try again" in r.json()["detail"].lower()


def test_login_throttle_clears_on_successful_login(client):
    from api.auth import LOGIN_MAX_FAILURES

    email = _new_email()
    password = "correct horse battery staple"
    client.post("/api/auth/signup", json={
        "email": email, "password": password, "name": "X", "state": "CT",
    })

    # One failure short of the limit, then a successful login.
    for _ in range(LOGIN_MAX_FAILURES - 1):
        r = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401

    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200

    # After the successful login the bucket should be empty, so we can
    # rack up another full window of failures without getting locked early.
    for _ in range(LOGIN_MAX_FAILURES - 1):
        r = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401, "throttle counter should have been cleared"


# ---------- 4. DELETE /me requires password ----------

def _signup_and_login(client, password="correct horse battery staple"):
    email = _new_email()
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "name": "X", "state": "CT",
    })
    assert r.status_code == 200
    return email, password, r.json()["token"]


def test_delete_me_without_body_returns_422(client):
    _, _, token = _signup_and_login(client)
    r = client.delete("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    # FastAPI maps missing required body to 422.
    assert r.status_code == 422, r.text


def test_delete_me_with_wrong_password_returns_401(client):
    _, _, token = _signup_and_login(client)
    r = client.request(
        "DELETE",
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "not-the-real-password"},
    )
    assert r.status_code == 401, r.text


def test_delete_me_with_right_password_succeeds(client):
    email, password, token = _signup_and_login(client)
    r = client.request(
        "DELETE",
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": password},
    )
    assert r.status_code == 200, r.text

    # Token now points at a deleted user — /me must 401, and CASCADE should
    # have cleaned up the session row.
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------- 5. Expired session pruning ----------

def test_new_session_prunes_expired_rows(client):
    """Insert an obviously-expired session row, then trigger a fresh login;
    the prune step in `_new_session` must remove it."""
    from datetime import datetime, timedelta, timezone

    from db import connect

    email, password, _ = _signup_and_login(client)

    # Stuff a stale session row directly into the DB. user_id doesn't matter
    # for the prune logic — it's filtered purely by expires_at.
    stale_token = "stale-token-for-prune-test"
    expired_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    with connect() as conn:
        # Borrow the user_id we just created so the FK is happy.
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        assert row is not None
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (stale_token, row["id"], expired_at),
        )

    # Sanity: the stale row exists pre-prune.
    with connect() as conn:
        present = conn.execute(
            "SELECT 1 FROM sessions WHERE token = ?", (stale_token,)
        ).fetchone()
        assert present is not None

    # A fresh login fires `_new_session`, which runs the prune.
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200

    with connect() as conn:
        gone = conn.execute(
            "SELECT 1 FROM sessions WHERE token = ?", (stale_token,)
        ).fetchone()
        assert gone is None, "stale session row should have been pruned by _new_session"
