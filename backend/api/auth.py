"""
Auth endpoints: signup, login, logout, me.

Stores users + opaque session tokens in the existing SQLite DB.
Tokens live in localStorage on the frontend and arrive via the
`Authorization: Bearer <token>` header.
"""

import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional


def _utcnow() -> datetime:
    """Naive UTC datetime — datetime.utcnow() is deprecated as of Python 3.12.
    Stays naive so it compares cleanly with the naive ISO strings SQLite
    round-trips for our TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from db import connect, init_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_TTL_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ISSUES = 10


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


# ---- Helpers ----

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _new_session(conn, user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(days=SESSION_TTL_DAYS)
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


# ---- Endpoints ----

@router.post("/signup")
async def signup(body: SignupBody):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")
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
async def login(body: LoginBody):
    email = body.email.strip().lower()
    _ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, name, state, issues, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row or not _verify_password(body.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
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
async def delete_me(user: dict = Depends(get_current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    return {"ok": True}
