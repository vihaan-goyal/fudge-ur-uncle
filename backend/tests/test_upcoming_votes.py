"""Tests for /api/upcoming-votes.

Covers empty DB, ordering, category filter, bad category, state filter, and
auth-based personalization. Mirrors the test_smoke.py fixture conventions.
"""
import sqlite3
import uuid
from datetime import date, timedelta


def _seed_votes(db_path, rows):
    """Insert scheduled_votes rows. `rows` is a list of dicts."""
    conn = sqlite3.connect(db_path)
    try:
        for r in rows:
            conn.execute(
                """INSERT OR REPLACE INTO scheduled_votes
                   (jurisdiction, state_code, bill_number, title, category,
                    scheduled_date, chamber)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("jurisdiction", "federal"),
                    r.get("state_code"),
                    r["bill_number"],
                    r["title"],
                    r["category"],
                    r["scheduled_date"].isoformat() if hasattr(r["scheduled_date"], "isoformat") else r["scheduled_date"],
                    r.get("chamber", "House"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _clear_votes(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM scheduled_votes")
        conn.commit()
    finally:
        conn.close()


def test_empty_returns_zero(client, _tmp_db_path):
    _clear_votes(_tmp_db_path)
    r = client.get("/api/upcoming-votes")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["votes"] == []


def test_orders_by_scheduled_date(client, _tmp_db_path):
    _clear_votes(_tmp_db_path)
    today = date.today()
    _seed_votes(_tmp_db_path, [
        {"bill_number": "HR-9001", "title": "Far", "category": "housing",
         "scheduled_date": today + timedelta(days=30)},
        {"bill_number": "HR-9002", "title": "Near", "category": "healthcare",
         "scheduled_date": today + timedelta(days=2)},
        {"bill_number": "HR-9003", "title": "Mid", "category": "environment",
         "scheduled_date": today + timedelta(days=14)},
    ])
    r = client.get("/api/upcoming-votes")
    assert r.status_code == 200
    bills = [v["bill_number"] for v in r.json()["votes"]]
    assert bills.index("HR-9002") < bills.index("HR-9003") < bills.index("HR-9001")


def test_categories_filter(client, _tmp_db_path):
    _clear_votes(_tmp_db_path)
    today = date.today()
    _seed_votes(_tmp_db_path, [
        {"bill_number": "HR-9101", "title": "h", "category": "healthcare",
         "scheduled_date": today + timedelta(days=1)},
        {"bill_number": "HR-9102", "title": "e", "category": "environment",
         "scheduled_date": today + timedelta(days=2)},
        {"bill_number": "HR-9103", "title": "d", "category": "defense",
         "scheduled_date": today + timedelta(days=3)},
    ])
    r = client.get("/api/upcoming-votes?categories=healthcare,environment")
    assert r.status_code == 200
    cats = {v["category"] for v in r.json()["votes"]}
    assert cats == {"healthcare", "environment"}


def test_bad_category_returns_400(client):
    r = client.get("/api/upcoming-votes?categories=bogus")
    assert r.status_code == 400


def test_state_filter_keeps_federal(client, _tmp_db_path):
    _clear_votes(_tmp_db_path)
    today = date.today()
    _seed_votes(_tmp_db_path, [
        {"jurisdiction": "federal", "state_code": None, "bill_number": "HR-9201",
         "title": "fed", "category": "healthcare",
         "scheduled_date": today + timedelta(days=1)},
        {"jurisdiction": "state", "state_code": "CT", "bill_number": "SB-9202",
         "title": "ct", "category": "education",
         "scheduled_date": today + timedelta(days=2)},
        {"jurisdiction": "state", "state_code": "NY", "bill_number": "AB-9203",
         "title": "ny", "category": "housing",
         "scheduled_date": today + timedelta(days=3)},
    ])
    r = client.get("/api/upcoming-votes?state=CT")
    assert r.status_code == 200
    bills = {v["bill_number"] for v in r.json()["votes"]}
    assert "HR-9201" in bills  # federal always included
    assert "SB-9202" in bills  # CT included
    assert "AB-9203" not in bills  # NY excluded


def test_auth_applies_stored_issues(client, _tmp_db_path):
    _clear_votes(_tmp_db_path)
    today = date.today()
    _seed_votes(_tmp_db_path, [
        {"bill_number": "HR-9301", "title": "h", "category": "healthcare",
         "scheduled_date": today + timedelta(days=1)},
        {"bill_number": "HR-9302", "title": "e", "category": "environment",
         "scheduled_date": today + timedelta(days=2)},
        {"bill_number": "HR-9303", "title": "d", "category": "defense",
         "scheduled_date": today + timedelta(days=3)},
    ])

    email = f"upcoming-{uuid.uuid4().hex[:8]}@test.local"
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "hunter2hunter", "name": "U", "state": "CT",
    })
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch("/api/auth/me", headers=headers,
                     json={"issues": ["healthcare"]})
    assert r.status_code == 200
    assert r.json()["user"]["issues"] == ["healthcare"]

    # Anonymous: all three categories present.
    r = client.get("/api/upcoming-votes")
    cats_anon = {v["category"] for v in r.json()["votes"]}
    assert {"healthcare", "environment", "defense"}.issubset(cats_anon)

    # Authenticated: defaults to user's issues.
    r = client.get("/api/upcoming-votes", headers=headers)
    body = r.json()
    cats_auth = {v["category"] for v in body["votes"]}
    assert cats_auth == {"healthcare"}
    assert body["filters"]["personalized"] is True

    # Explicit query overrides personalization.
    r = client.get("/api/upcoming-votes?categories=environment", headers=headers)
    body = r.json()
    cats_explicit = {v["category"] for v in body["votes"]}
    assert cats_explicit == {"environment"}
    assert body["filters"]["personalized"] is False
