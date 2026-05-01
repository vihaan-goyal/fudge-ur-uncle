"""
Alert pipeline runner.

Joins recent donations against upcoming scheduled votes, runs the scoring
formula on each candidate pair, and writes qualifying alerts to the DB.

Usage:
    python -m backend.alerts.pipeline                 # run with defaults
    ALERTS_DONATION_LOOKBACK_DAYS=30 python -m ...    # override windows
"""

import json
from dataclasses import asdict
from datetime import date, timedelta
from typing import Optional

from ..db import connect
from . import config
from .scoring import (
    Donation,
    ScheduledVote,
    Baseline,
    score_alert,
    should_alert,
    format_alert_text,
)


# ---------- DB read helpers ----------

def _fetch_recent_donations(
    conn, lookback_days: int, actor_type: str = "federal"
) -> list[tuple[int, Donation, str, str]]:
    """Return (donation_id, Donation, actor_type, actor_id) for donations in the window."""
    cutoff = date.today() - timedelta(days=lookback_days)
    cursor = conn.execute(
        """SELECT id, actor_type, actor_id, pac_name, industry, amount, donation_date
           FROM donations
           WHERE actor_type = ? AND donation_date >= ?
           ORDER BY donation_date DESC""",
        (actor_type, cutoff),
    )
    out = []
    for row in cursor:
        d = Donation(
            amount=row["amount"],
            donation_date=date.fromisoformat(row["donation_date"]) if isinstance(row["donation_date"], str) else row["donation_date"],
            industry=row["industry"],
            pac_name=row["pac_name"],
        )
        out.append((row["id"], d, row["actor_type"], row["actor_id"]))
    return out


def _fetch_upcoming_votes(
    conn, lookahead_days: int, jurisdiction: str = "federal", state_code: Optional[str] = None
) -> list[tuple[int, ScheduledVote]]:
    """Return (vote_id, ScheduledVote) for votes in the lookahead window."""
    today = date.today()
    cutoff = today + timedelta(days=lookahead_days)
    if state_code is None:
        cursor = conn.execute(
            """SELECT id, bill_number, title, category, scheduled_date
               FROM scheduled_votes
               WHERE jurisdiction = ? AND scheduled_date >= ? AND scheduled_date <= ?
               ORDER BY scheduled_date ASC""",
            (jurisdiction, today, cutoff),
        )
    else:
        cursor = conn.execute(
            """SELECT id, bill_number, title, category, scheduled_date
               FROM scheduled_votes
               WHERE jurisdiction = ? AND state_code = ? AND scheduled_date >= ? AND scheduled_date <= ?
               ORDER BY scheduled_date ASC""",
            (jurisdiction, state_code, today, cutoff),
        )
    out = []
    for row in cursor:
        v = ScheduledVote(
            bill_number=row["bill_number"],
            title=row["title"],
            category=row["category"],
            scheduled_date=date.fromisoformat(row["scheduled_date"]) if isinstance(row["scheduled_date"], str) else row["scheduled_date"],
        )
        out.append((row["id"], v))
    return out


def _fetch_baseline(conn, actor_type: str, actor_id: str, industry: str) -> Optional[Baseline]:
    """Look up the precomputed baseline for (actor, industry); None if missing."""
    row = conn.execute(
        """SELECT mean_amount, stddev_amount, n_samples
           FROM industry_baselines
           WHERE actor_type = ? AND actor_id = ? AND industry = ?""",
        (actor_type, actor_id, industry),
    ).fetchone()
    if not row or row["n_samples"] < config.BASELINE_MIN_SAMPLES:
        return None
    return Baseline(
        mean_amount=row["mean_amount"],
        stddev_amount=row["stddev_amount"],
        n_samples=row["n_samples"],
    )


def _count_news_mentions(conn, bill_number: str, category: str) -> int:
    """Count news mentions in the lookback window matching this bill or topic."""
    cutoff = date.today() - timedelta(days=config.NEWS_LOOKBACK_DAYS)
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM news_mentions
           WHERE published_at >= ?
             AND (bill_number = ? OR topic = ?)""",
        (cutoff, bill_number, category),
    ).fetchone()
    return int(row["n"]) if row else 0


# ---------- Baseline computation ----------

def recompute_baselines(conn) -> int:
    """
    Recompute (mean, stddev, n) for every (actor, industry) pair from history.

    Excludes the most recent 60 days so a recent suspicious donation
    doesn't pollute its own baseline. Returns the number of baselines written.
    """
    cutoff = date.today() - timedelta(days=60)
    cursor = conn.execute(
        """SELECT actor_type, actor_id, industry,
                  AVG(amount) AS mean_amount,
                  COUNT(*)    AS n_samples
           FROM donations
           WHERE donation_date < ?
           GROUP BY actor_type, actor_id, industry""",
        (cutoff,),
    )

    written = 0
    for row in cursor.fetchall():
        # SQLite doesn't have STDDEV built in; compute it manually
        amounts = [
            r["amount"] for r in conn.execute(
                """SELECT amount FROM donations
                   WHERE actor_type = ? AND actor_id = ? AND industry = ? AND donation_date < ?""",
                (row["actor_type"], row["actor_id"], row["industry"], cutoff),
            )
        ]
        n = len(amounts)
        if n < 2:
            stddev = 0.0
        else:
            mean = sum(amounts) / n
            variance = sum((a - mean) ** 2 for a in amounts) / (n - 1)
            stddev = variance ** 0.5

        conn.execute(
            """INSERT INTO industry_baselines
               (actor_type, actor_id, industry, mean_amount, stddev_amount, n_samples, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(actor_type, actor_id, industry) DO UPDATE SET
                 mean_amount = excluded.mean_amount,
                 stddev_amount = excluded.stddev_amount,
                 n_samples = excluded.n_samples,
                 updated_at = CURRENT_TIMESTAMP""",
            (row["actor_type"], row["actor_id"], row["industry"], row["mean_amount"], stddev, n),
        )
        written += 1
    return written


# ---------- Alert write ----------

def _upsert_alert(
    conn, actor_type: str, actor_id: str, donation_id: int, vote_id: int,
    score: float, urgent: bool, headline: str, body: str, signals_json: str,
) -> bool:
    """Insert or update an alert. Returns True if newly inserted."""
    existing = conn.execute(
        """SELECT id FROM alerts
           WHERE actor_type = ? AND actor_id = ? AND donation_id = ? AND vote_id = ?""",
        (actor_type, actor_id, donation_id, vote_id),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE alerts SET score = ?, urgent = ?, headline = ?,
                                  body = ?, signals_json = ?
               WHERE id = ?""",
            (score, urgent, headline, body, signals_json, existing["id"]),
        )
        return False

    conn.execute(
        """INSERT INTO alerts
           (actor_type, actor_id, donation_id, vote_id, score, urgent,
            headline, body, signals_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (actor_type, actor_id, donation_id, vote_id, score, urgent,
         headline, body, signals_json),
    )
    return True


# ---------- Main pipeline ----------

def _run_for_jurisdiction(
    conn, actor_type: str, jurisdiction: str, stats: dict
) -> None:
    """Score (donation x vote) pairs for one side of the world (federal or state).

    Federal donations are paired only with federal votes; state with state.
    The signal-scoring formula itself is identity-agnostic, but we don't
    want a federal rep's donations matched against a state bill or vice versa.
    """
    donations = _fetch_recent_donations(conn, config.DONATION_LOOKBACK_DAYS, actor_type=actor_type)
    votes = _fetch_upcoming_votes(conn, config.VOTE_LOOKAHEAD_DAYS, jurisdiction=jurisdiction)
    stats["donations_considered"] += len(donations)
    stats["votes_considered"] += len(votes)
    print(f"[pipeline] {actor_type}: {len(donations)} donations x {len(votes)} votes")

    if not donations or not votes:
        return

    news_cache = {
        (v.bill_number, v.category): _count_news_mentions(conn, v.bill_number, v.category)
        for _, v in votes
    }

    for donation_id, donation, a_type, a_id in donations:
        baseline = _fetch_baseline(conn, a_type, a_id, donation.industry)
        for vote_id, vote in votes:
            stats["pairs_scored"] += 1
            news_count = news_cache[(vote.bill_number, vote.category)]

            signals = score_alert(
                donation=donation, vote=vote, baseline=baseline,
                news_article_count=news_count,
            )
            if not should_alert(signals):
                continue

            headline, body = format_alert_text(donation, vote, signals)
            signals_json = json.dumps(asdict(signals))
            was_new = _upsert_alert(
                conn, a_type, a_id, donation_id, vote_id,
                signals.score, signals.urgent, headline, body, signals_json,
            )
            if was_new:
                stats["alerts_written_new"] += 1
            else:
                stats["alerts_updated"] += 1
            if signals.urgent:
                stats["alerts_urgent"] += 1


def run_pipeline() -> dict:
    """
    Score every (recent donation, upcoming vote) pair and write alerts.

    Runs federal and state independently so cross-jurisdiction pairs (e.g. a
    federal rep's donation against a state bill) don't get scored.

    Returns a stats dict for logging.
    """
    config.print_config()

    stats = {
        "donations_considered": 0,
        "votes_considered": 0,
        "pairs_scored": 0,
        "alerts_written_new": 0,
        "alerts_updated": 0,
        "alerts_urgent": 0,
        "baselines_computed": 0,
    }

    with connect() as conn:
        # Baselines are computed across both jurisdictions in one pass —
        # the GROUP BY already includes actor_type so federal/state stay separate.
        stats["baselines_computed"] = recompute_baselines(conn)
        print(f"[pipeline] Recomputed {stats['baselines_computed']} baselines")

        _run_for_jurisdiction(conn, actor_type="federal", jurisdiction="federal", stats=stats)
        _run_for_jurisdiction(conn, actor_type="state", jurisdiction="state", stats=stats)

    print(f"[pipeline] Done. Stats: {stats}")
    return stats


if __name__ == "__main__":
    run_pipeline()