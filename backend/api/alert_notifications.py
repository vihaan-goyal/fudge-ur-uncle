"""Urgent-alert email notifications.

Called at the tail of `alerts.refresh.run()`. Finds urgent un-dismissed alerts
that haven't been emailed to the relevant users yet and sends one email per
(alert, user) pair via Resend.

Matching rule
-------------
A user receives an alert email when ALL of these hold:
  - alert.urgent = 1, alert.dismissed = 0
  - user.email_verified = 1, notify_alerts = 1, email_bouncing = 0
  - user.state matches the rep's state (federal: legislators-current lookup;
    state: scheduled_votes.state_code)
  - alert.category is in user.issues (JSON array of category keys)

Dedupe is via `alert_email_sends(alert_id, user_id)` — INSERT OR IGNORE so a
re-running pipeline never double-sends. Rows clean themselves up when the
alert is stale-swept (FK CASCADE).
"""

import json
from typing import Optional

from db import connect
from api.email_sender import send_email
from api import legislators
import config


# Subject is short — Gmail's mobile preview clips around 35 chars on the
# subject line. Lead with the urgency cue and the rep name.
_SUBJECT_PREFIX = "Urgent: "


async def _bioguide_to_state_map() -> dict[str, str]:
    """Return bioguide_id -> state-code. Reads the in-process legislators
    cache (or fetches it once). Falls back to sample data if GitHub is
    unreachable — same contract as the rest of the app."""
    legs = await legislators.fetch_legislators()
    out: dict[str, str] = {}
    for leg in legs:
        bioguide = (leg.get("id") or {}).get("bioguide")
        terms = leg.get("terms") or []
        if not bioguide or not terms:
            continue
        state = (terms[-1] or {}).get("state")
        if state:
            out[bioguide] = state.upper()
    return out


def _parse_issues(raw: Optional[str]) -> set[str]:
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(x).lower() for x in parsed if x}


def _rep_name_for_alert(actor_type: str, actor_id: str, leg_map_by_id: dict[str, dict]) -> str:
    """Best-effort display name. Falls back to the bare ID so the email still
    composes when the legislator cache misses — better than dropping the row."""
    leg = leg_map_by_id.get(actor_id)
    if leg:
        name = (leg.get("name") or {})
        return name.get("official_full") or f"{name.get('first','')} {name.get('last','')}".strip() or actor_id
    return actor_id


def _build_email(
    *, user_name: str, rep_name: str, headline: str, body: str,
    bill_number: str, category: str, scheduled_date: str,
) -> tuple[str, str, str]:
    """Returns (subject, html, text)."""
    greeting = user_name.strip() or "there"
    subject = f"{_SUBJECT_PREFIX}{rep_name} · {category}"
    text = (
        f"Hi {greeting},\n\n"
        f"An urgent alert just landed on {rep_name}:\n\n"
        f"{headline}\n"
        f"{body}\n\n"
        f"Bill: {bill_number}\n"
        f"Scheduled: {scheduled_date}\n"
        f"Category: {category}\n\n"
        f"Open the app to see the full breakdown and take action:\n"
        f"{config.FRONTEND_URL}\n\n"
        f"You're getting this because '{category}' is in your tracked issues. "
        f"Manage email preferences inside the app's Settings screen.\n"
    )
    html = (
        f"<p>Hi {greeting},</p>"
        f"<p>An urgent alert just landed on <strong>{rep_name}</strong>:</p>"
        f"<p><strong>{headline}</strong><br/>{body}</p>"
        f"<ul>"
        f"<li>Bill: {bill_number}</li>"
        f"<li>Scheduled: {scheduled_date}</li>"
        f"<li>Category: {category}</li>"
        f"</ul>"
        f'<p><a href="{config.FRONTEND_URL}">Open Fudge Ur Uncle</a> to see the full breakdown and take action.</p>'
        f"<p style=\"font-size:11px;color:#777\">"
        f"You're getting this because '{category}' is in your tracked issues. "
        f"Manage email preferences in the app's Settings screen."
        f"</p>"
    )
    return subject, html, text


async def notify_pending_urgent_alerts() -> dict:
    """Scan urgent alerts that haven't been emailed yet, send one email per
    (alert, user) pair. Returns a stats dict for logging.

    Safe to call repeatedly — the dedupe ledger ensures users only receive
    one email per alert. Failures during send are recorded with delivered=0
    so we don't keep retrying a dead address.
    """
    stats = {
        "candidates_scanned": 0,
        "matches_attempted": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "users_eligible": 0,
    }

    bioguide_to_state = await _bioguide_to_state_map()
    # Same legislators cache, indexed for name lookup
    leg_by_bioguide = {
        (leg.get("id") or {}).get("bioguide"): leg
        for leg in await legislators.fetch_legislators()
        if (leg.get("id") or {}).get("bioguide")
    }

    with connect() as conn:
        # Pull every eligible user once. The number of users is much smaller
        # than the candidate alert set in practice, so re-querying per alert
        # would be wasteful.
        users = conn.execute(
            """SELECT id, email, name, state, issues
               FROM users
               WHERE notify_alerts = 1
                 AND email_verified = 1
                 AND email_bouncing = 0
                 AND state IS NOT NULL"""
        ).fetchall()
        stats["users_eligible"] = len(users)
        if not users:
            return stats

        # Index users by state so per-alert lookup is O(1) on state.
        users_by_state: dict[str, list] = {}
        user_issues: dict[int, set[str]] = {}
        for u in users:
            users_by_state.setdefault((u["state"] or "").upper(), []).append(u)
            user_issues[u["id"]] = _parse_issues(u["issues"])

        # Candidates: urgent un-dismissed alerts not yet emailed to at least
        # one user. (We still per-(alert, user) gate in the inner loop; the
        # outer filter just avoids re-scanning fully-processed alerts.)
        candidate_rows = conn.execute(
            """SELECT a.id AS alert_id, a.actor_type, a.actor_id,
                      a.headline, a.body,
                      v.bill_number, v.category, v.scheduled_date, v.state_code,
                      v.jurisdiction
               FROM alerts a
               JOIN scheduled_votes v ON v.id = a.vote_id
               WHERE a.urgent = 1 AND a.dismissed = 0"""
        ).fetchall()
        stats["candidates_scanned"] = len(candidate_rows)

        for row in candidate_rows:
            actor_type = row["actor_type"]
            actor_id = row["actor_id"]
            category = (row["category"] or "").lower()
            jurisdiction = row["jurisdiction"]

            # Determine the rep's state for matching.
            if jurisdiction == "federal":
                rep_state = bioguide_to_state.get(actor_id)
            else:
                rep_state = (row["state_code"] or "").upper() or None
            if not rep_state:
                continue

            recipients = users_by_state.get(rep_state.upper(), [])
            if not recipients:
                continue

            rep_name = _rep_name_for_alert(actor_type, actor_id, leg_by_bioguide)
            scheduled_date = str(row["scheduled_date"] or "")
            for u in recipients:
                if category not in user_issues.get(u["id"], set()):
                    continue
                # Skip if already sent. INSERT OR IGNORE would also work but
                # we want to skip the email build entirely.
                already = conn.execute(
                    "SELECT 1 FROM alert_email_sends WHERE alert_id = ? AND user_id = ?",
                    (row["alert_id"], u["id"]),
                ).fetchone()
                if already:
                    continue

                stats["matches_attempted"] += 1
                subject, html, text = _build_email(
                    user_name=u["name"] or "",
                    rep_name=rep_name,
                    headline=row["headline"] or "",
                    body=row["body"] or "",
                    bill_number=row["bill_number"] or "",
                    category=category,
                    scheduled_date=scheduled_date,
                )
                ok = await send_email(
                    to=u["email"], subject=subject, html=html, text=text,
                )
                conn.execute(
                    "INSERT INTO alert_email_sends (alert_id, user_id, delivered) "
                    "VALUES (?, ?, ?)",
                    (row["alert_id"], u["id"], 1 if ok else 0),
                )
                if ok:
                    stats["emails_sent"] += 1
                else:
                    stats["emails_failed"] += 1

    return stats
