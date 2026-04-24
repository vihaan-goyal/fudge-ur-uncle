"""
Persistent cache for expensive AI-derived results (promise scoring, stance
analysis). Backed by the same SQLite file the alerts pipeline uses.

Why: GPT-4o-mini + site scraping per rep takes 30-90s and costs money; a
server restart shouldn't drop everything. TTL-based so a rep's record can
go stale as new votes land.

Table is created lazily on first use, so this module works even if the
user hasn't run `python -m backend.db` yet.
"""
import json
from datetime import datetime, timedelta

from db import connect

_table_ready = False


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                cache_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_cache_expires ON ai_cache(expires_at)")
    _table_ready = True


def get(key: str):
    """Return the cached value for `key`, or None if missing/expired."""
    try:
        _ensure_table()
        with connect() as conn:
            row = conn.execute(
                "SELECT value_json, expires_at FROM ai_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] < datetime.utcnow():
            return None
        return json.loads(row["value_json"])
    except Exception as e:
        print(f"[ai_cache] get({key}) failed ({e})")
        return None


def set(key: str, value, ttl_hours: int = 168) -> None:
    """Store `value` (JSON-serializable) under `key` with a TTL. Default 7 days."""
    try:
        _ensure_table()
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_cache (cache_key, value_json, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    created_at = CURRENT_TIMESTAMP,
                    expires_at = excluded.expires_at
                """,
                (key, json.dumps(value), expires_at),
            )
    except Exception as e:
        print(f"[ai_cache] set({key}) failed ({e})")
