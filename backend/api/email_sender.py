"""Transactional email via Resend's HTTP API.

Stays a one-function module — verification + reset are the only two messages
we send, so abstracting templates further would be premature. When
`RESEND_API_KEY` is unset we log the link instead of sending; that path keeps
local dev usable without a Resend account and stops a missing key from
breaking signup.
"""

import httpx

from config import RESEND_API_KEY, RESEND_FROM


RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(*, to: str, subject: str, html: str, text: str) -> bool:
    """Send a single transactional email. Returns True on success or dev-log
    fallback. Never raises — auth flows treat email as fire-and-forget so a
    flaky Resend dependency can't 500 a signup."""
    if not RESEND_API_KEY:
        print(f"[email_sender] RESEND_API_KEY unset; would send to {to}: {subject}")
        print(f"[email_sender] body (text):\n{text}")
        return True

    payload = {
        "from": RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(RESEND_API_URL, json=payload, headers=headers)
        if r.status_code >= 400:
            print(f"[email_sender] Resend {r.status_code} for {to}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[email_sender] send failed for {to}: {e}")
        return False
