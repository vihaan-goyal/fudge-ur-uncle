"""
Auth endpoints: signup, login, logout, me.

Stores users + opaque session tokens in the existing SQLite DB.
Tokens live in localStorage on the frontend and arrive via the
`Authorization: Bearer <token>` header.
"""

import json
import os
import re
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Deque, Dict, List, Optional, Tuple


def _utcnow() -> datetime:
    """Naive UTC datetime — datetime.utcnow() is deprecated as of Python 3.12.
    Stays naive so it compares cleanly with the naive ISO strings SQLite
    round-trips for our TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from db import connect, init_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_TTL_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ISSUES = 10

# Login throttle. In-process and per-(client-IP, email) — locks brute-force
# against a single email without nuking shared NAT. State is module-level so it
# survives request handlers but not server restarts; that's the price of not
# wiring a Redis dependency for a hackathon-grade app. With multiple uvicorn
# workers each worker has its own counter, so the effective limit scales with
# worker count — fine for our threat model.
LOGIN_MAX_FAILURES = int(os.environ.get("FUU_LOGIN_MAX_FAILURES", "8"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("FUU_LOGIN_WINDOW_SECONDS", str(15 * 60)))
_login_failures: Dict[Tuple[str, str], Deque[float]] = {}
_login_failures_lock = threading.Lock()

# Pre-hashed unguessable string. Used in `login` when the email isn't found so
# bcrypt still runs on every call — flattens the timing channel that would
# otherwise let an attacker enumerate registered emails.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("utf-8")

# Trivially-bad passwords. Not meant to be exhaustive — a determined attacker
# clears this list trivially, but it stops the most embarrassing signups
# (`password123` etc.) without dragging in a megabyte wordlist.
_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password12", "password123", "passw0rd",
    "12345678", "123456789", "1234567890", "12345678910",
    "qwerty123", "qwertyuiop", "qwerty1234",
    "iloveyou", "iloveyou1", "iloveyou123",
    "admin1234", "admin12345",
    "welcome1", "welcome123",
    "letmein", "letmein1", "letmein123",
    "abcd1234", "abc12345", "abc123456",
    "11111111", "00000000", "55555555",
    "monkey123", "dragon123", "master123",
    "football1", "baseball1", "sunshine1",
    "princess1", "shadow123",
    "changeme", "changeme1", "changeme123",
})


def _client_ip(request: Optional[Request]) -> str:
    if request is None or request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def _login_throttle_check(ip: str, email: str) -> int:
    """Return seconds-until-reset if locked, 0 otherwise. Doesn't mutate."""
    key = (ip, email)
    now = monotonic()
    cutoff = now - LOGIN_WINDOW_SECONDS
    with _login_failures_lock:
        bucket = _login_failures.get(key)
        if not bucket:
            return 0
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if not bucket:
            _login_failures.pop(key, None)
            return 0
        if len(bucket) >= LOGIN_MAX_FAILURES:
            return max(1, int(LOGIN_WINDOW_SECONDS - (now - bucket[0])))
        return 0


def _login_throttle_record_failure(ip: str, email: str) -> None:
    key = (ip, email)
    now = monotonic()
    with _login_failures_lock:
        bucket = _login_failures.setdefault(key, deque())
        bucket.append(now)


def _login_throttle_clear(ip: str, email: str) -> None:
    with _login_failures_lock:
        _login_failures.pop((ip, email), None)


def _login_throttle_reset_all() -> None:
    """Test-only hook so the harness doesn't carry state between cases."""
    with _login_failures_lock:
        _login_failures.clear()


def _validate_password_strength(password: str, email: str) -> None:
    """Reject the most embarrassing passwords. Length already gated by Pydantic.

    Only invoked at signup; existing accounts with weak passwords keep working.
    """
    pw_lower = password.lower()
    if pw_lower in _COMMON_PASSWORDS:
        raise HTTPException(status_code=400, detail="Password is too common")
    local_part = email.split("@", 1)[0].lower() if "@" in email else email.lower()
    if pw_lower == email.lower() or (local_part and pw_lower == local_part):
        raise HTTPException(status_code=400, detail="Password cannot match your email")


# ---- Schemas ----

class SignupBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(..., min_length=1, max_length=120)
    state: Optional[str] = Field(None, min_length=2, max_length=2)


class LoginBody(BaseModel):
    email: str
    password: str


class UpdateMeBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    state: Optional[str] = Field(None, min_length=2, max_length=2)
    issues: Optional[List[str]] = Field(None, max_length=MAX_ISSUES)


class DeleteMeBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


# ---- Helpers ----

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _new_session(conn, user_id: int) -> tuple[str, datetime]:
    now = _utcnow()
    # Opportunistic prune — cheap because sessions has an index on expires_at,
    # and only fires on signup/login (not every request). Keeps the table from
    # accumulating garbage indefinitely.
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    return token, expires_at


def _user_payload(row) -> dict:
    issues = None
    raw_issues = row["issues"] if "issues" in row.keys() else None
    if raw_issues:
        try:
            parsed = json.loads(raw_issues)
            if isinstance(parsed, list):
                issues = [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            issues = None
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "state": row["state"],
        "issues": issues,
    }


_schema_ready = False


def _ensure_schema():
    """Lazy-init so auth works even if `python -m backend.db` was never run."""
    global _schema_ready
    if _schema_ready:
        return
    init_db()
    _schema_ready = True


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency for endpoints that require auth."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    _ensure_schema()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.name, u.state, u.issues, s.expires_at
              FROM sessions s
              JOIN users u ON u.id = s.user_id
             WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    # PARSE_DECLTYPES converters key off the column type in the *table*; through
    # a JOIN sqlite3 sometimes hands back the raw ISO string instead of a
    # datetime. Coerce explicitly so the comparison below isn't lexicographic.
    exp = row["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < _utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    return _user_payload(row)


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    """Like `get_current_user` but returns None on missing/invalid token
    instead of raising. Lets endpoints accept anonymous traffic while still
    applying user preferences when a valid session is present."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


# ---- Endpoints ----

@router.post("/signup")
async def signup(body: SignupBody):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")
    _validate_password_strength(body.password, email)
    state = body.state.upper() if body.state else None

    _ensure_schema()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        cur = conn.execute(
            "INSERT INTO users (email, password_hash, name, state) VALUES (?, ?, ?, ?)",
            (email, _hash_password(body.password), body.name.strip(), state),
        )
        user_id = cur.lastrowid
        token, expires_at = _new_session(conn, user_id)
        row = conn.execute(
            "SELECT id, email, name, state, issues FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "user": _user_payload(row),
    }


@router.post("/login")
async def login(body: LoginBody, request: Request):
    email = body.email.strip().lower()
    ip = _client_ip(request)

    locked_for = _login_throttle_check(ip, email)
    if locked_for:
        minutes = max(1, locked_for // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {minutes} minute(s).",
        )

    _ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, name, state, issues, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        # Always run bcrypt to avoid leaking "is this email registered?" via
        # response timing. The dummy hash is unguessable.
        hashed = row["password_hash"] if row else _DUMMY_PASSWORD_HASH
        password_ok = _verify_password(body.password, hashed)
        if not row or not password_ok:
            _login_throttle_record_failure(ip, email)
            raise HTTPException(status_code=401, detail="Invalid email or password")
        _login_throttle_clear(ip, email)
        token, expires_at = _new_session(conn, row["id"])

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "user": _user_payload(row),
    }


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"ok": True}
    token = authorization.split(None, 1)[1].strip()
    _ensure_schema()
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": user}


@router.patch("/me")
async def update_me(body: UpdateMeBody, user: dict = Depends(get_current_user)):
    fields = []
    values = []
    if body.name is not None:
        fields.append("name = ?")
        values.append(body.name.strip())
    if body.state is not None:
        fields.append("state = ?")
        values.append(body.state.upper())
    if body.issues is not None:
        cleaned = [i.strip() for i in body.issues if i and i.strip()]
        fields.append("issues = ?")
        values.append(json.dumps(cleaned))
    if not fields:
        return {"user": user}
    values.append(user["id"])
    with connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        row = conn.execute(
            "SELECT id, email, name, state, issues FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    return {"user": _user_payload(row)}


@router.delete("/me")
async def delete_me(body: DeleteMeBody, user: dict = Depends(get_current_user)):
    # Re-verify password — a stolen bearer token alone shouldn't be enough to
    # nuke the account. FK CASCADE on `sessions.user_id` cleans up sessions.
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if not row or not _verify_password(body.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    return {"ok": True}
