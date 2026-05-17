"""Resend webhook receiver.

Resend uses Svix-style signed webhooks: a `webhook-id` + `webhook-timestamp`
+ `webhook-signature` header trio, where the signature is HMAC-SHA256 of
`{id}.{timestamp}.{body}` keyed by the base64-decoded secret. We verify
manually (no svix dependency) — the spec is short enough.

Events we care about:
  email.bounced     — hard bounce. Latch users.email_bouncing=1 and silence
                      notify_alerts so the next pipeline tick doesn't retry.
  email.complained  — recipient hit "spam". Same treatment as bounce; we
                      stop emailing anyone who reports us.
  email.delivery_delayed — soft signal, ignored for now.
  email.delivered   — ignored.
  email.opened/clicked — ignored.

Webhook handlers are public (Resend can't authenticate to us) so signature
verification is the only gate. A missing secret fails closed.
"""

import base64
import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from db import connect
import config


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# Resend sends both `svix-*` and `webhook-*` headers (Svix renamed during the
# migration; legacy receivers stayed on the old names). Accept either so a
# future dashboard change doesn't break verification.
_ID_HEADERS = ("webhook-id", "svix-id")
_TS_HEADERS = ("webhook-timestamp", "svix-timestamp")
_SIG_HEADERS = ("webhook-signature", "svix-signature")

# How much clock skew we tolerate between Resend and us. Svix recommends 5
# minutes — anything outside that window we treat as a replay attempt.
_MAX_TIMESTAMP_SKEW_SECONDS = 5 * 60


def _pick_header(request: Request, candidates: tuple[str, ...]) -> Optional[str]:
    for name in candidates:
        val = request.headers.get(name)
        if val:
            return val
    return None


def _decode_secret(secret: str) -> bytes:
    """Resend secrets are prefixed `whsec_` followed by base64. Older Svix
    secrets just contain the raw base64. Accept both."""
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    # Padding fix — base64 can be missing trailing `=` when copied from a
    # dashboard. urlsafe_b64decode is lenient if we pad it ourselves.
    pad = (-len(secret)) % 4
    return base64.b64decode(secret + ("=" * pad))


def _verify_signature(*, secret: str, message_id: str, timestamp: str, body: bytes, signature_header: str) -> bool:
    """Constant-time verify of the Svix signature header.

    The header is a space-delimited list of `v1,base64` chunks — there can
    be multiple (key rotation), and a match against any one is sufficient.
    """
    if not (message_id and timestamp and signature_header):
        return False
    try:
        signed = f"{message_id}.{timestamp}.".encode() + body
        key = _decode_secret(secret)
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    except Exception:
        return False
    for piece in signature_header.split():
        if "," not in piece:
            continue
        _, _, sig = piece.partition(",")
        if hmac.compare_digest(sig, expected):
            return True
    return False


def _timestamp_ok(timestamp: str) -> bool:
    """Reject replays older than _MAX_TIMESTAMP_SKEW_SECONDS or further in
    the future than that. Treat malformed timestamps as failures."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    import time
    now = int(time.time())
    return abs(now - ts) <= _MAX_TIMESTAMP_SKEW_SECONDS


def _disable_for_email(conn, email: str) -> int:
    """Flip notify_alerts off + latch email_bouncing on for whoever owns
    this address. Returns rows affected — 0 means we don't have an account
    for the bounced address, which is fine (logged-out signups whose verify
    email bounced after they deleted their account, etc.)."""
    cur = conn.execute(
        "UPDATE users SET notify_alerts = 0, email_bouncing = 1 "
        "WHERE LOWER(email) = LOWER(?)",
        (email,),
    )
    return cur.rowcount


@router.post("/resend")
async def resend_webhook(request: Request):
    """Receive a Resend webhook event. Returns 200 on every recognized + valid
    event so Resend stops retrying; returns 4xx for bad signatures (replay /
    forgery) so the dashboard surfaces the misconfiguration."""
    if not config.RESEND_WEBHOOK_SECRET:
        # Fail closed — without a secret we can't tell real events from
        # forged ones. Return 503 so Resend retries while we wire the secret.
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    body = await request.body()
    message_id = _pick_header(request, _ID_HEADERS)
    timestamp = _pick_header(request, _TS_HEADERS)
    signature = _pick_header(request, _SIG_HEADERS)
    if not (message_id and timestamp and signature):
        raise HTTPException(status_code=400, detail="Missing signature headers")

    if not _timestamp_ok(timestamp):
        raise HTTPException(status_code=400, detail="Timestamp out of tolerance")

    if not _verify_signature(
        secret=config.RESEND_WEBHOOK_SECRET,
        message_id=message_id,
        timestamp=timestamp,
        body=body,
        signature_header=signature,
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type") or ""
    data = payload.get("data") or {}
    # `to` is a list of strings in Resend's payload; can be empty on some
    # event types.
    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]

    if event_type in ("email.bounced", "email.complained"):
        if not recipients:
            return {"ok": True, "ignored": "no recipients in payload"}
        with connect() as conn:
            affected = 0
            for addr in recipients:
                if not isinstance(addr, str) or not addr:
                    continue
                affected += _disable_for_email(conn, addr)
        print(f"[resend-webhook] {event_type}: disabled {affected} account(s) for {recipients}")
        return {"ok": True, "event": event_type, "disabled": affected}

    # Other event types: acknowledge but no-op. Returning 200 stops the
    # retry loop on Resend's side.
    return {"ok": True, "event": event_type, "ignored": True}
