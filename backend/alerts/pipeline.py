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
from datetime import date, datetime, timedelta, timezone
from typing import Optional


def _utcnow_iso() -> str:
    """Match the format the ai_cache adapter writes — naive UTC ISO with 'T'.

    SQLite's CURRENT_TIMESTAMP is space-separated, so comparing it lexically
    against stored ISO-with-T values misjudges any expiry within the current
    day (T > space).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

try:
    from ..db import connect
except ImportError:
    from db import connect
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
                                  body = ?, signals_json = ?,
                                  updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (score, urgent, headline, body, signals_json, existing["id"]),
        )
        return False

    conn.execute(
        """INSERT INTO alerts
           (actor_type, actor_id, donation_id, vote_id, score, urgent,
            headline, body, signals_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (actor_type, actor_id, donation_id, vote_id, score, urgent,
         headline, body, signals_json),
    )
    return True


# ---------- Main pipeline ----------

def _state_for_actor_map(conn) -> dict[str, str]:
    """Build a `people_id -> state-code` map from cached Legiscan rosters.

    Reads ai_cache rows keyed `legiscan:people:{STATE}` (per-state roster) and
    `legiscan:profile:{people_id}` (individual profile) to learn which state
    each state actor belongs to. Falls back to SAMPLE_STATE_LEGISLATORS so the
    no-key dev path still groups donations correctly.

    Without this map a state actor's donations get paired with every state's
    bills (CT senator vs. NJ housing bill).
    """
    out: dict[str, str] = {}

    # Two import paths: `backend.api.legiscan` works when run via
    # `python -m backend.alerts.pipeline` (project root); `api.legiscan` works
    # when backend/ is on sys.path (e.g. `python server.py` from backend/).
    sample_roster = None
    for mod_path in ("backend.api.legiscan", "api.legiscan"):
        try:
            mod = __import__(mod_path, fromlist=["SAMPLE_STATE_LEGISLATORS"])
            sample_roster = getattr(mod, "SAMPLE_STATE_LEGISLATORS", None)
            if sample_roster is not None:
                break
        except Exception:
            continue
    if sample_roster:
        for state, roster in sample_roster.items():
            for r in roster:
                pid = r.get("people_id")
                if pid is not None:
                    out[str(pid)] = state.upper()

    now_iso = _utcnow_iso()
    try:
        rows = conn.execute(
            """SELECT value_json FROM ai_cache
               WHERE cache_key LIKE 'legiscan:people:%'
                 AND expires_at > ?""",
            (now_iso,),
        ).fetchall()
        for row in rows:
            try:
                roster = json.loads(row["value_json"])
            except Exception:
                continue
            if not isinstance(roster, list):
                continue
            for r in roster:
                pid = r.get("people_id")
                state = r.get("state")
                if pid is not None and state:
                    out[str(pid)] = state.upper()
    except Exception as e:
        print(f"[pipeline] roster cache scan failed ({e})")

    try:
        rows = conn.execute(
            """SELECT value_json FROM ai_cache
               WHERE cache_key LIKE 'legiscan:profile:%'
                 AND expires_at > ?""",
            (now_iso,),
        ).fetchall()
        for row in rows:
            try:
                profile = json.loads(row["value_json"])
            except Exception:
                continue
            if not isinstance(profile, dict):
                continue
            pid = profile.get("people_id")
            state = profile.get("state")
            if pid is not None and state:
                out.setdefault(str(pid), state.upper())
    except Exception as e:
        print(f"[pipeline] profile cache scan failed ({e})")

    return out


def _score_pairs(
    conn,
    donations: list,
    votes: list,
    actor_type: str,
    stats: dict,
    seen_pairs: set[tuple[int, int]],
) -> None:
    """Score every donation x vote pair in this group and write qualifying alerts.

    `seen_pairs` is mutated to record every (donation_id, vote_id) that was
    upserted; the caller uses it to sweep stale alert rows after the run.
    """
    if not donations or not votes:
        return

    news_cache = {
        (v.bill_number, v.category): _count_news_mentions(conn, v.bill_number, v.category)
        for _, v in votes
    }

    # State-side calibration: FTM aggregates are lifetime stamps with a
    # today date, and state actors lack baselines almost universally. The
    # honest R/A values for these are flat-proxy and zero respectively;
    # without this dampening, every state alert lands above the urgent
    # threshold purely because R=1.0 and A=0.5. Federal scoring is unchanged.
    is_state = actor_type == "state"
    proxy_r = config.PROXY_DONATION_R if is_state else None
    no_baseline_a = config.NO_BASELINE_A_HONEST if is_state else None

    for donation_id, donation, a_type, a_id in donations:
        baseline = _fetch_baseline(conn, a_type, a_id, donation.industry)
        for vote_id, vote in votes:
            stats["pairs_scored"] += 1
            news_count = news_cache[(vote.bill_number, vote.category)]

            signals = score_alert(
                donation=donation, vote=vote, baseline=baseline,
                news_article_count=news_count,
                proxy_donation_r=proxy_r,
                no_baseline_a=no_baseline_a,
            )
            if not should_alert(signals):
                continue

            headline, body = format_alert_text(donation, vote, signals)
            signals_json = json.dumps(asdict(signals))
            was_new = _upsert_alert(
                conn, a_type, a_id, donation_id, vote_id,
                signals.score, signals.urgent, headline, body, signals_json,
            )
            seen_pairs.add((donation_id, vote_id))
            if was_new:
                stats["alerts_written_new"] += 1
            else:
                stats["alerts_updated"] += 1
            if signals.urgent:
                stats["alerts_urgent"] += 1


def _sweep_stale_alerts(
    conn, actor_type: str, seen_pairs: set[tuple[int, int]], stats: dict
) -> None:
    """Delete non-dismissed alerts whose (donation_id, vote_id) wasn't refreshed this run.

    Three reasons a previously-written alert can go stale:
      1. The donation aged out of the lookback window.
      2. The scheduled vote already happened (or moved out of lookahead).
      3. The recomputed score no longer clears `should_alert` — usually
         because scoring config changed (e.g. state-side calibration).

    Dismissed alerts are kept so user-suppressed history doesn't resurface
    if the same pair becomes alert-worthy again.
    """
    rows = conn.execute(
        "SELECT id, donation_id, vote_id FROM alerts "
        "WHERE actor_type = ? AND dismissed = 0",
        (actor_type,),
    ).fetchall()
    stale = [r["id"] for r in rows if (r["donation_id"], r["vote_id"]) not in seen_pairs]
    if not stale:
        return
    # Chunk the IN-list to stay under SQLite's parameter limit (default 999).
    for i in range(0, len(stale), 500):
        chunk = stale[i:i + 500]
        placeholders = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM alerts WHERE id IN ({placeholders})", chunk)
    stats["alerts_swept_stale"] += len(stale)
    print(f"[pipeline] {actor_type}: swept {len(stale)} stale alert rows")


def _run_for_jurisdiction(
    conn, actor_type: str, jurisdiction: str, stats: dict
) -> None:
    """Score (donation x vote) pairs for one side of the world (federal or state).

    Federal donations are paired only with federal votes; state with state.
    For state, donations are further grouped by the actor's state so a CT
    senator's donations don't get paired with NJ bills. The signal-scoring
    formula itself is identity-agnostic — this scoping happens at the
    candidate-pair level.
    """
    donations = _fetch_recent_donations(conn, config.DONATION_LOOKBACK_DAYS, actor_type=actor_type)
    seen_pairs: set[tuple[int, int]] = set()

    if actor_type == "state":
        state_map = _state_for_actor_map(conn)
        groups: dict[str, list] = {}
        unmapped = 0
        for tup in donations:
            actor_id = tup[3]
            state = state_map.get(str(actor_id))
            if not state:
                unmapped += 1
                continue
            groups.setdefault(state, []).append(tup)
        if unmapped:
            print(f"[pipeline] state: {unmapped} donations skipped (no state mapping in cache)")

        for state, state_donations in groups.items():
            votes = _fetch_upcoming_votes(
                conn, config.VOTE_LOOKAHEAD_DAYS,
                jurisdiction=jurisdiction, state_code=state,
            )
            stats["donations_considered"] += len(state_donations)
            stats["votes_considered"] += len(votes)
            print(f"[pipeline] state {state}: {len(state_donations)} donations x {len(votes)} votes")
            _score_pairs(conn, state_donations, votes, actor_type, stats, seen_pairs)
        _sweep_stale_alerts(conn, actor_type, seen_pairs, stats)
        return

    votes = _fetch_upcoming_votes(conn, config.VOTE_LOOKAHEAD_DAYS, jurisdiction=jurisdiction)
    stats["donations_considered"] += len(donations)
    stats["votes_considered"] += len(votes)
    print(f"[pipeline] {actor_type}: {len(donations)} donations x {len(votes)} votes")
    _score_pairs(conn, donations, votes, actor_type, stats, seen_pairs)
    _sweep_stale_alerts(conn, actor_type, seen_pairs, stats)


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
        "alerts_swept_stale": 0,
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