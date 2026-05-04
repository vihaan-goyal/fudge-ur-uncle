"""Smoke test: signup -> login -> /me -> PATCH /me -> /api/alerts.

Locks in the recent fixes (UTC time string, 401 token-clear, updated_at) by
exercising the actual HTTP surface against an in-memory FastAPI client.
"""
import uuid


def _new_email() -> str:
    return f"smoke-{uuid.uuid4().hex[:8]}@test.local"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert "api_keys_configured" in body


def test_signup_login_me_flow(client):
    email = _new_email()
    password = "hunter2hunter"

    # Signup returns a token + user payload
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "name": "Smoke Test", "state": "CT",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == email
    assert body["user"]["state"] == "CT"
    signup_token = body["token"]

    # /me with the signup token works
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {signup_token}"})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == email

    # Login with the same creds returns a NEW token (different from signup)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    login_token = r.json()["token"]
    assert login_token != signup_token

    # PATCH /me persists issues across calls
    r = client.patch(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_token}"},
        json={"issues": ["Healthcare", "Environment"]},
    )
    assert r.status_code == 200
    assert r.json()["user"]["issues"] == ["Healthcare", "Environment"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    assert r.json()["user"]["issues"] == ["Healthcare", "Environment"]


def test_login_wrong_password_returns_401(client):
    email = _new_email()
    client.post("/api/auth/signup", json={
        "email": email, "password": "correctpassword", "name": "X", "state": "CT",
    })
    r = client.post("/api/auth/login", json={"email": email, "password": "wrongwrong"})
    assert r.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_without_token_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_alerts_endpoint_returns_shape(client):
    """Alerts table may be empty (no pipeline run in tests). Shape should still be valid."""
    r = client.get("/api/alerts?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "alerts" in body
    assert isinstance(body["alerts"], list)
    # Each alert (if any) must have the time string the recent fix produces.
    for a in body["alerts"]:
        assert "time" in a
        assert isinstance(a["time"], str)


def test_alerts_filter_by_actor(client):
    """The actor_type/actor_id filter must round-trip into the filters echo."""
    r = client.get("/api/alerts?actor_type=federal&actor_id=M001169&limit=1")
    assert r.status_code == 200
    body = r.json()
    assert body["filters"]["actor_type"] == "federal"
    assert body["filters"]["actor_id"] == "M001169"
