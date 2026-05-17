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
from api.email_sender import send_email
import config

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_TTL_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ISSUES = 10
ELIGIBILITY_VALUES = frozenset({"citizen", "naturalizing", "green_card", "not_sure"})

# TTLs for one-shot email tokens. Verify is generous because users might leave
# the email sitting in their inbox; reset is short so a leaked screenshot of
# a reset email doesn't stay actionable for long.
VERIFY_TOKEN_TTL_HOURS = 24
RESET_TOKEN_TTL_MINUTES = 60

# Per-(ip, action) caps. Same in-process bucket as the login throttle, with
# its own counter so verify-resend churn can't lock out a fresh login attempt.
EMAIL_THROTTLE_MAX = int(os.environ.get("FUU_EMAIL_THROTTLE_MAX", "5"))
EMAIL_THROTTLE_WINDOW_SECONDS = int(os.environ.get("FUU_EMAIL_THROTTLE_WINDOW_SECONDS", str(60 * 60)))
_email_throttle: Dict[Tuple[str, str, str], Deque[float]] = {}
_email_throttle_lock = threading.Lock()

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
    eligibility: Optional[str] = Field(None, min_length=1, max_length=32)
    notify_alerts: Optional[bool] = None


class DeleteMeBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


class VerifyEmailBody(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)


class ForgotPasswordBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class ResetPasswordBody(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)
    password: str = Field(..., min_length=8, max_length=200)


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
    eligibility = row["eligibility"] if "eligibility" in row.keys() else None
    email_verified = bool(row["email_verified"]) if "email_verified" in row.keys() else False
    notify_alerts = bool(row["notify_alerts"]) if "notify_alerts" in row.keys() else True
    email_bouncing = bool(row["email_bouncing"]) if "email_bouncing" in row.keys() else False
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "state": row["state"],
        "issues": issues,
        "eligibility": eligibility,
        "email_verified": email_verified,
        "notify_alerts": notify_alerts,
        "email_bouncing": email_bouncing,
    }


def _email_throttle_check_and_record(ip: str, action: str, key: str) -> int:
    """Check + record in one shot for outbound email actions. Returns 0 when
    the call is allowed (and the bucket has been incremented), or remaining
    seconds when the cap was already hit."""
    bucket_key = (ip, action, key)
    now = monotonic()
    cutoff = now - EMAIL_THROTTLE_WINDOW_SECONDS
    with _email_throttle_lock:
        bucket = _email_throttle.setdefault(bucket_key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= EMAIL_THROTTLE_MAX:
            return max(1, int(EMAIL_THROTTLE_WINDOW_SECONDS - (now - bucket[0])))
        bucket.append(now)
        return 0


def _email_throttle_reset_all() -> None:
    """Test-only hook."""
    with _email_throttle_lock:
        _email_throttle.clear()


def _issue_one_shot_token(conn, table: str, user_id: int, ttl: timedelta) -> str:
    """Insert and return a fresh one-shot token. Caller is responsible for
    deleting prior tokens for this user when that's the intended semantic
    (verify and reset both prune-then-issue)."""
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + ttl
    conn.execute(
        f"INSERT INTO {table} (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    return token


def _redeem_one_shot_token(conn, table: str, token: str) -> Optional[int]:
    """Look up a one-shot token, delete it, and return user_id if valid (and
    not expired). Returns None for unknown/expired tokens. Always deletes —
    even an expired row is consumed so users can't keep retrying stale links."""
    row = conn.execute(
        f"SELECT user_id, expires_at FROM {table} WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        return None
    conn.execute(f"DELETE FROM {table} WHERE token = ?", (token,))
    exp = row["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < _utcnow():
        return None
    return row["user_id"]


def _build_verify_email(name: str, link: str) -> tuple[str, str, str]:
    """Returns (subject, html, text). Plain-language and short — the more it
    looks like a transactional email the less likely it lands in spam."""
    subject = "Verify your Fudge Ur Uncle email"
    greeting = name.strip() or "there"
    text = (
        f"Hi {greeting},\n\n"
        f"Tap the link below to confirm your email on Fudge Ur Uncle. The "
        f"link expires in {VERIFY_TOKEN_TTL_HOURS} hours.\n\n"
        f"{link}\n\n"
        f"If you didn't create an account, you can ignore this email.\n"
    )
    html = (
        f"<p>Hi {greeting},</p>"
        f"<p>Tap the link below to confirm your email on Fudge Ur Uncle. "
        f"The link expires in {VERIFY_TOKEN_TTL_HOURS} hours.</p>"
        f'<p><a href="{link}">Verify my email</a></p>'
        f"<p>If you didn't create an account, you can ignore this email.</p>"
    )
    return subject, html, text


def _build_reset_email(name: str, link: str) -> tuple[str, str, str]:
    subject = "Reset your Fudge Ur Uncle password"
    greeting = name.strip() or "there"
    text = (
        f"Hi {greeting},\n\n"
        f"Tap the link below to choose a new password. The link expires in "
        f"{RESET_TOKEN_TTL_MINUTES} minutes.\n\n"
        f"{link}\n\n"
        f"If you didn't ask for this, ignore the email — your password is "
        f"unchanged.\n"
    )
    html = (
        f"<p>Hi {greeting},</p>"
        f"<p>Tap the link below to choose a new password. The link expires "
        f"in {RESET_TOKEN_TTL_MINUTES} minutes.</p>"
        f'<p><a href="{link}">Reset my password</a></p>'
        f"<p>If you didn't ask for this, ignore the email — your password "
        f"is unchanged.</p>"
    )
    return subject, html, text


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
            SELECT u.id, u.email, u.name, u.state, u.issues, u.eligibility,
                   u.email_verified, u.notify_alerts, u.email_bouncing,
                   s.expires_at
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
        verify_token = _issue_one_shot_token(
            conn, "email_verifications", user_id, timedelta(hours=VERIFY_TOKEN_TTL_HOURS)
        )
        row = conn.execute(
            "SELECT id, email, name, state, issues, eligibility, email_verified, notify_alerts, email_bouncing FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    # Fire-and-forget — a flaky email provider can't 500 a signup. Failures are
    # logged in email_sender; user can hit /resend-verification from the banner.
    link = f"{config.FRONTEND_URL}/?verify={verify_token}"
    subject, html, text = _build_verify_email(body.name, link)
    try:
        await send_email(to=email, subject=subject, html=html, text=text)
    except Exception as e:
        print(f"[auth.signup] verify email send raised: {e}")

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
            "SELECT id, email, name, state, issues, eligibility, email_verified, "
            "notify_alerts, email_bouncing, password_hash "
            "FROM users WHERE email = ?",
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
    if body.eligibility is not None:
        if body.eligibility not in ELIGIBILITY_VALUES:
            raise HTTPException(status_code=400, detail="Invalid eligibility value")
        fields.append("eligibility = ?")
        values.append(body.eligibility)
    if body.notify_alerts is not None:
        fields.append("notify_alerts = ?")
        values.append(1 if body.notify_alerts else 0)
    if not fields:
        return {"user": user}
    values.append(user["id"])
    with connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        row = conn.execute(
            "SELECT id, email, name, state, issues, eligibility, email_verified, notify_alerts, email_bouncing FROM users WHERE id = ?", (user["id"],)
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


# ---- Email verification ----

@router.post("/verify-email")
async def verify_email(body: VerifyEmailBody):
    """Redeem a verification token. Marks the user email_verified=1 and
    deletes the token row. Idempotent on re-submit (second call returns 400
    because the token is now gone) — fine for our flow where the link is
    one-shot anyway."""
    _ensure_schema()
    with connect() as conn:
        user_id = _redeem_one_shot_token(conn, "email_verifications", body.token)
        if user_id is None:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        conn.execute(
            "UPDATE users SET email_verified = 1, email_verified_at = ? WHERE id = ?",
            (_utcnow(), user_id),
        )
        row = conn.execute(
            "SELECT id, email, name, state, issues, eligibility, email_verified, notify_alerts, email_bouncing FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        # User deleted account between issuance and redeem — token was already
        # cascaded away, but cover the race anyway.
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {"user": _user_payload(row)}


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Re-send a fresh verification email. Throttled per (IP, user-id) so a
    compromised session can't blast the user with mail. No-op when already
    verified — returns ok so the UI doesn't need to gate the button."""
    if user.get("email_verified"):
        return {"ok": True, "already_verified": True}

    ip = _client_ip(request)
    locked_for = _email_throttle_check_and_record(ip, "resend_verify", str(user["id"]))
    if locked_for:
        minutes = max(1, locked_for // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {minutes} minute(s).",
        )

    _ensure_schema()
    with connect() as conn:
        # Single live token per user — prune prior entries so old emails
        # become dead links. The new token is the only one that still works.
        conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user["id"],))
        verify_token = _issue_one_shot_token(
            conn, "email_verifications", user["id"], timedelta(hours=VERIFY_TOKEN_TTL_HOURS)
        )

    link = f"{config.FRONTEND_URL}/?verify={verify_token}"
    subject, html, text = _build_verify_email(user.get("name") or "", link)
    sent = await send_email(to=user["email"], subject=subject, html=html, text=text)
    return {"ok": True, "sent": sent}


# ---- Password reset ----

@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordBody, request: Request):
    """Email a reset link to the address, IF it's a registered user. Always
    returns 200 with the same payload to avoid email-enumeration via response
    diff. Throttled per (IP, email) so this isn't a free spam endpoint."""
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        # Same generic response — don't tell the caller their input was bad.
        return {"ok": True}

    ip = _client_ip(request)
    locked_for = _email_throttle_check_and_record(ip, "forgot_password", email)
    if locked_for:
        # Same response shape — caller can't tell whether they were throttled
        # or just hit a non-account. The bucket already absorbed the call.
        return {"ok": True}

    _ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row:
            return {"ok": True}
        # Single live reset per user so prior links stop working as soon as
        # the user re-requests. Same hygiene as resend-verification.
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (row["id"],))
        reset_token = _issue_one_shot_token(
            conn, "password_resets", row["id"], timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        )
        name = row["name"]

    link = f"{config.FRONTEND_URL}/?reset={reset_token}"
    subject, html, text = _build_reset_email(name or "", link)
    try:
        await send_email(to=email, subject=subject, html=html, text=text)
    except Exception as e:
        print(f"[auth.forgot_password] send raised: {e}")
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordBody):
    """Redeem a reset token + set a new password. On success we also nuke
    every active session for the user — a password change implies "kick all
    other devices" by convention, and it also blocks an attacker who somehow
    got the bearer token from coexisting after the legitimate user resets."""
    _ensure_schema()
    with connect() as conn:
        # Need the email first so password-strength validation can compare.
        row = conn.execute(
            "SELECT u.id, u.email FROM password_resets pr "
            "JOIN users u ON u.id = pr.user_id "
            "WHERE pr.token = ?",
            (body.token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        user_id = _redeem_one_shot_token(conn, "password_resets", body.token)
        if user_id is None:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        _validate_password_strength(body.password, row["email"])
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(body.password), user_id),
        )
        # Invalidate every session for this user — the only way to revoke a
        # bearer token without a refresh-token layer.
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"ok": True}
