"""
SQLite storage for the alerts pipeline.

Tables:
- donations: PAC donations to legislators (from FEC filings)
- scheduled_votes: upcoming floor votes (from Congress.gov)
- news_mentions: recent news articles mentioning a bill or topic
- alerts: generated alerts (what the frontend reads)
- industry_baselines: per-rep/per-industry historical stats for anomaly detection
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

# Tests set FUU_DB_PATH to a tmp file so they don't clobber dev data.
DB_PATH = Path(os.environ.get("FUU_DB_PATH") or Path(__file__).parent / "data" / "whoboughtmyrep.sqlite")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# Python 3.12+: register explicit adapters/converters instead of relying on defaults
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


SCHEMA = """
CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type TEXT NOT NULL DEFAULT 'federal',
    actor_id TEXT NOT NULL,
    pac_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    amount REAL NOT NULL,
    donation_date DATE NOT NULL,
    fec_filing_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_donations_actor ON donations(actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_donations_industry ON donations(industry);
CREATE INDEX IF NOT EXISTS idx_donations_date ON donations(donation_date);

CREATE TABLE IF NOT EXISTS scheduled_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction TEXT NOT NULL DEFAULT 'federal',
    state_code TEXT,
    bill_number TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    scheduled_date DATE NOT NULL,
    chamber TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (jurisdiction, state_code, bill_number)
);
CREATE INDEX IF NOT EXISTS idx_votes_category ON scheduled_votes(category);
CREATE INDEX IF NOT EXISTS idx_votes_date ON scheduled_votes(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_votes_jurisdiction ON scheduled_votes(jurisdiction, state_code);

CREATE TABLE IF NOT EXISTS news_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT,
    topic TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    headline TEXT,
    published_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_news_topic ON news_mentions(topic);
CREATE INDEX IF NOT EXISTS idx_news_bill ON news_mentions(bill_number);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_mentions(published_at);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type TEXT NOT NULL DEFAULT 'federal',
    actor_id TEXT NOT NULL,
    donation_id INTEGER NOT NULL,
    vote_id INTEGER NOT NULL,
    score REAL NOT NULL,
    urgent BOOLEAN NOT NULL DEFAULT 0,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Bumped every time the pipeline reconfirms the alert (insert OR upsert).
    -- Used for the "X mins ago" string so re-run alerts feel fresh; created_at
    -- still records first appearance.
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dismissed BOOLEAN DEFAULT 0,
    FOREIGN KEY (donation_id) REFERENCES donations(id),
    FOREIGN KEY (vote_id) REFERENCES scheduled_votes(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique
    ON alerts(actor_type, actor_id, donation_id, vote_id);
CREATE INDEX IF NOT EXISTS idx_alerts_score ON alerts(score DESC);

CREATE TABLE IF NOT EXISTS industry_baselines (
    actor_type TEXT NOT NULL DEFAULT 'federal',
    actor_id TEXT NOT NULL,
    industry TEXT NOT NULL,
    mean_amount REAL NOT NULL,
    stddev_amount REAL NOT NULL,
    n_samples INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_type, actor_id, industry)
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_cache_expires ON ai_cache(expires_at);

-- Maps an actor (federal bioguide_id or state Legiscan people_id) to its
-- ID in an external dataset (FTM eid, OpenSecrets ID, FEC candidate ID, etc.).
-- Lets us pull data from multiple sources without leaking their IDs into
-- the rest of the schema.
CREATE TABLE IF NOT EXISTS external_ids (
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_type, actor_id, source)
);
CREATE INDEX IF NOT EXISTS idx_external_ids_reverse ON external_ids(source, external_id);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    state TEXT,
    issues TEXT,
    eligibility TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    email_verified_at TIMESTAMP,
    -- notify_alerts: per-user opt-in for urgent-alert emails. Defaults on; the
    -- Resend webhook flips this off when a bounce/complaint event comes in,
    -- and the Settings screen toggle lets the user opt back in.
    notify_alerts INTEGER NOT NULL DEFAULT 1,
    -- email_bouncing: latched flag set by the webhook on hard bounce. Even if
    -- the user re-enables notify_alerts, this stays on until they update
    -- their email address. Treat (notify_alerts=1 AND email_bouncing=0) as
    -- the gate before sending.
    email_bouncing INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- One-shot tokens for email verification (sent on signup, redeemed via
-- POST /api/auth/verify-email). Row deleted on redeem; expired rows pruned
-- opportunistically when a new token is issued for the same user.
CREATE TABLE IF NOT EXISTS email_verifications (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_email_verifications_user ON email_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_email_verifications_expires ON email_verifications(expires_at);

-- One-shot tokens for password reset (sent via POST /forgot-password,
-- redeemed via POST /reset-password). Row deleted on use.
CREATE TABLE IF NOT EXISTS password_resets (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_expires ON password_resets(expires_at);

-- Dedupe ledger for urgent-alert emails. The notification pass scans urgent
-- alerts on every refresh tick; INSERT OR IGNORE on (alert_id, user_id) means
-- each user receives exactly one email per alert even if the pipeline runs
-- repeatedly. Alert deletion cascades — a stale-swept alert frees the slot
-- in case the same (donation, vote) pair becomes alert-worthy again later.
CREATE TABLE IF NOT EXISTS alert_email_sends (
    alert_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (alert_id, user_id),
    FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_alert_email_sends_user ON alert_email_sends(user_id);
"""


@contextmanager
def connect():
    """Yield a sqlite3 connection with row factory set."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Bring an existing DB up to current shape, then create anything missing.

    Migration runs first because SCHEMA contains indexes that reference columns
    that legacy DBs don't have yet — the CREATE INDEX would fail otherwise.
    """
    # Migrations run on a separate connection so we can toggle FK enforcement
    # — table-recreate steps need it off.
    _migrate()
    with connect() as conn:
        conn.executescript(SCHEMA)
    print(f"[db] Initialized at {DB_PATH}")


def _table_columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate() -> None:
    """Idempotent in-place migrations for DBs created before a column existed.

    Safe to run repeatedly — each step checks current schema first.
    """
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        # FK off for the duration; some steps recreate tables that others reference.
        conn.execute("PRAGMA foreign_keys = OFF")

        # users.issues (added with the auth feature)
        u_cols = _table_columns(conn, "users")
        if u_cols and "issues" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN issues TEXT")

        # users.eligibility — drives Mamu framing + Learn-to-Vote + dashboard tile.
        u_cols = _table_columns(conn, "users")
        if u_cols and "eligibility" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN eligibility TEXT")

        # users.email_verified + email_verified_at — soft gate, banner shows
        # in the UI until the user clicks the verification link.
        u_cols = _table_columns(conn, "users")
        if u_cols and "email_verified" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        if u_cols and "email_verified_at" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP")

        # users.notify_alerts + email_bouncing — drive urgent-alert email
        # notifications (off by webhook, on by Settings toggle).
        u_cols = _table_columns(conn, "users")
        if u_cols and "notify_alerts" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN notify_alerts INTEGER NOT NULL DEFAULT 1")
        if u_cols and "email_bouncing" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email_bouncing INTEGER NOT NULL DEFAULT 0")

        # donations: bioguide_id -> actor_id (+ actor_type discriminator)
        d_cols = _table_columns(conn, "donations")
        if d_cols and "bioguide_id" in d_cols and "actor_id" not in d_cols:
            conn.execute("ALTER TABLE donations RENAME COLUMN bioguide_id TO actor_id")
            conn.execute("ALTER TABLE donations ADD COLUMN actor_type TEXT NOT NULL DEFAULT 'federal'")
            conn.execute("DROP INDEX IF EXISTS idx_donations_rep")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_actor ON donations(actor_type, actor_id)")

        # alerts: same shape change
        a_cols = _table_columns(conn, "alerts")
        if a_cols and "bioguide_id" in a_cols and "actor_id" not in a_cols:
            conn.execute("ALTER TABLE alerts RENAME COLUMN bioguide_id TO actor_id")
            conn.execute("ALTER TABLE alerts ADD COLUMN actor_type TEXT NOT NULL DEFAULT 'federal'")
            conn.execute("DROP INDEX IF EXISTS idx_alerts_unique")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique "
                "ON alerts(actor_type, actor_id, donation_id, vote_id)"
            )

        # alerts.updated_at — added so the relative-time string reflects last
        # reconfirm time, not first-appearance time. Backfill from created_at
        # so legacy rows render correctly until the next pipeline run.
        # SQLite forbids non-constant defaults in ALTER TABLE ADD COLUMN, so
        # the column is added without a default and backfilled in a second step.
        a_cols = _table_columns(conn, "alerts")
        if a_cols and "updated_at" not in a_cols:
            conn.execute("ALTER TABLE alerts ADD COLUMN updated_at TIMESTAMP")
            conn.execute("UPDATE alerts SET updated_at = created_at WHERE updated_at IS NULL")

        # industry_baselines: PK changes, so table swap (rename column alone won't shift the PK)
        b_cols = _table_columns(conn, "industry_baselines")
        if b_cols and "bioguide_id" in b_cols and "actor_id" not in b_cols:
            conn.executescript("""
                CREATE TABLE industry_baselines_new (
                    actor_type TEXT NOT NULL DEFAULT 'federal',
                    actor_id TEXT NOT NULL,
                    industry TEXT NOT NULL,
                    mean_amount REAL NOT NULL,
                    stddev_amount REAL NOT NULL,
                    n_samples INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (actor_type, actor_id, industry)
                );
                INSERT INTO industry_baselines_new
                    (actor_type, actor_id, industry, mean_amount, stddev_amount, n_samples, updated_at)
                    SELECT 'federal', bioguide_id, industry, mean_amount, stddev_amount, n_samples, updated_at
                    FROM industry_baselines;
                DROP TABLE industry_baselines;
                ALTER TABLE industry_baselines_new RENAME TO industry_baselines;
            """)

        # scheduled_votes: bill_number UNIQUE -> (jurisdiction, state_code, bill_number) UNIQUE
        v_cols = _table_columns(conn, "scheduled_votes")
        if v_cols and "jurisdiction" not in v_cols:
            conn.executescript("""
                CREATE TABLE scheduled_votes_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jurisdiction TEXT NOT NULL DEFAULT 'federal',
                    state_code TEXT,
                    bill_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    scheduled_date DATE NOT NULL,
                    chamber TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (jurisdiction, state_code, bill_number)
                );
                INSERT INTO scheduled_votes_new
                    (id, jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber, created_at)
                    SELECT id, 'federal', NULL, bill_number, title, category, scheduled_date, chamber, created_at
                    FROM scheduled_votes;
                DROP TABLE scheduled_votes;
                ALTER TABLE scheduled_votes_new RENAME TO scheduled_votes;
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_category ON scheduled_votes(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_date ON scheduled_votes(scheduled_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_jurisdiction ON scheduled_votes(jurisdiction, state_code)")

        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()