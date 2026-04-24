"""
SQLite storage for the alerts pipeline.

Tables:
- donations: PAC donations to legislators (from FEC filings)
- scheduled_votes: upcoming floor votes (from Congress.gov)
- news_mentions: recent news articles mentioning a bill or topic
- alerts: generated alerts (what the frontend reads)
- industry_baselines: per-rep/per-industry historical stats for anomaly detection
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "whoboughtmyrep.sqlite"
DB_PATH.parent.mkdir(exist_ok=True)


# Python 3.12+: register explicit adapters/converters instead of relying on defaults
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


SCHEMA = """
CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bioguide_id TEXT NOT NULL,
    pac_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    amount REAL NOT NULL,
    donation_date DATE NOT NULL,
    fec_filing_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_donations_rep ON donations(bioguide_id);
CREATE INDEX IF NOT EXISTS idx_donations_industry ON donations(industry);
CREATE INDEX IF NOT EXISTS idx_donations_date ON donations(donation_date);

CREATE TABLE IF NOT EXISTS scheduled_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    scheduled_date DATE NOT NULL,
    chamber TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_votes_category ON scheduled_votes(category);
CREATE INDEX IF NOT EXISTS idx_votes_date ON scheduled_votes(scheduled_date);

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
    bioguide_id TEXT NOT NULL,
    donation_id INTEGER NOT NULL,
    vote_id INTEGER NOT NULL,
    score REAL NOT NULL,
    urgent BOOLEAN NOT NULL DEFAULT 0,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dismissed BOOLEAN DEFAULT 0,
    FOREIGN KEY (donation_id) REFERENCES donations(id),
    FOREIGN KEY (vote_id) REFERENCES scheduled_votes(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique
    ON alerts(bioguide_id, donation_id, vote_id);
CREATE INDEX IF NOT EXISTS idx_alerts_score ON alerts(score DESC);

CREATE TABLE IF NOT EXISTS industry_baselines (
    bioguide_id TEXT NOT NULL,
    industry TEXT NOT NULL,
    mean_amount REAL NOT NULL,
    stddev_amount REAL NOT NULL,
    n_samples INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bioguide_id, industry)
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_cache_expires ON ai_cache(expires_at);
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
    """Create all tables if they don't exist."""
    with connect() as conn:
        conn.executescript(SCHEMA)
    print(f"[db] Initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()