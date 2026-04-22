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

def _fetch_recent_donations(conn, lookback_days: int) -> list[tuple[int, Donation, str]]:
    """Return (donation_id, Donation, bioguide_id) for donations in the lookback window."""
    cutoff = date.today() - timedelta(days=lookback_days)
    cursor = conn.execute(
        """SELECT id, bioguide_id, pac_name, industry, amount, donation_date
           FROM donations
           WHERE donation_date >= ?
           ORDER BY donation_date DESC""",
        (cutoff,),
    )
    out = []
    for row in cursor:
        d = Donation(
            amount=row["amount"],
            donation_date=date.fromisoformat(row["donation_date"]) if isinstance(row["donation_date"], str) else row["donation_date"],
            industry=row["industry"],
            pac_name=row["pac_name"],
        )
        out.append((row["id"], d, row["bioguide_id"]))
    return out


def _fetch_upcoming_votes(conn, lookahead_days: int) -> list[tuple[int, ScheduledVote]]:
    """Return (vote_id, ScheduledVote) for votes in the lookahead window."""
    today = date.today()
    cutoff = today + timedelta(days=lookahead_days)
    cursor = conn.execute(
        """SELECT id, bill_number, title, category, scheduled_date
           FROM scheduled_votes
           WHERE scheduled_date >= ? AND scheduled_date <= ?
           ORDER BY scheduled_date ASC""",
        (today, cutoff),
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


def _fetch_baseline(conn, bioguide_id: str, industry: str) -> Optional[Baseline]:
    """Look up the precomputed baseline for (rep, industry); None if missing."""
    row = conn.execute(
        """SELECT mean_amount, stddev_amount, n_samples
           FROM industry_baselines
           WHERE bioguide_id = ? AND industry = ?""",
        (bioguide_id, industry),
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
    Recompute (mean, stddev, n) for every (rep, industry) pair from history.

    Excludes the most recent 60 days so a recent suspicious donation
    doesn't pollute its own baseline. Returns the number of baselines written.
    """
    cutoff = date.today() - timedelta(days=60)
    cursor = conn.execute(
        """SELECT bioguide_id, industry,
                  AVG(amount) AS mean_amount,
                  COUNT(*)    AS n_samples
           FROM donations
           WHERE donation_date < ?
           GROUP BY bioguide_id, industry""",
        (cutoff,),
    )

    written = 0
    for row in cursor.fetchall():
        # SQLite doesn't have STDDEV built in; compute it manually
        amounts = [
            r["amount"] for r in conn.execute(
                """SELECT amount FROM donations
                   WHERE bioguide_id = ? AND industry = ? AND donation_date < ?""",
                (row["bioguide_id"], row["industry"], cutoff),
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
               (bioguide_id, industry, mean_amount, stddev_amount, n_samples, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(bioguide_id, industry) DO UPDATE SET
                 mean_amount = excluded.mean_amount,
                 stddev_amount = excluded.stddev_amount,
                 n_samples = excluded.n_samples,
                 updated_at = CURRENT_TIMESTAMP""",
            (row["bioguide_id"], row["industry"], row["mean_amount"], stddev, n),
        )
        written += 1
    return written


# ---------- Alert write ----------

def _upsert_alert(
    conn, bioguide_id: str, donation_id: int, vote_id: int,
    score: float, urgent: bool, headline: str, body: str, signals_json: str,
) -> bool:
    """Insert or update an alert. Returns True if newly inserted."""
    existing = conn.execute(
        """SELECT id FROM alerts
           WHERE bioguide_id = ? AND donation_id = ? AND vote_id = ?""",
        (bioguide_id, donation_id, vote_id),
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
           (bioguide_id, donation_id, vote_id, score, urgent,
            headline, body, signals_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (bioguide_id, donation_id, vote_id, score, urgent,
         headline, body, signals_json),
    )
    return True


# ---------- Main pipeline ----------

def run_pipeline() -> dict:
    """
    Score every (recent donation, upcoming vote) pair and write alerts.

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
        # 1. Refresh baselines from history
        stats["baselines_computed"] = recompute_baselines(conn)
        print(f"[pipeline] Recomputed {stats['baselines_computed']} baselines")

        # 2. Pull candidates
        donations = _fetch_recent_donations(conn, config.DONATION_LOOKBACK_DAYS)
        votes = _fetch_upcoming_votes(conn, config.VOTE_LOOKAHEAD_DAYS)
        stats["donations_considered"] = len(donations)
        stats["votes_considered"] = len(votes)
        print(f"[pipeline] Considering {len(donations)} donations x {len(votes)} votes")

        if not donations or not votes:
            print("[pipeline] Nothing to score.")
            return stats

        # 3. Cache news counts per (bill, category) - avoid repeat queries
        news_cache = {
            (v.bill_number, v.category): _count_news_mentions(conn, v.bill_number, v.category)
            for _, v in votes
        }

        # 4. Score every pair
        for donation_id, donation, bioguide_id in donations:
            baseline = _fetch_baseline(conn, bioguide_id, donation.industry)

            for vote_id, vote in votes:
                stats["pairs_scored"] += 1
                news_count = news_cache[(vote.bill_number, vote.category)]

                signals = score_alert(
                    donation=donation,
                    vote=vote,
                    baseline=baseline,
                    news_article_count=news_count,
                )

                if not should_alert(signals):
                    continue

                headline, body = format_alert_text(donation, vote, signals)
                signals_json = json.dumps(asdict(signals))
                was_new = _upsert_alert(
                    conn, bioguide_id, donation_id, vote_id,
                    signals.score, signals.urgent,
                    headline, body, signals_json,
                )
                if was_new:
                    stats["alerts_written_new"] += 1
                else:
                    stats["alerts_updated"] += 1
                if signals.urgent:
                    stats["alerts_urgent"] += 1

    print(f"[pipeline] Done. Stats: {stats}")
    return stats


if __name__ == "__main__":
    run_pipeline()