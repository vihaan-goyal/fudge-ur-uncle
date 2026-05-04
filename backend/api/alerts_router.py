"""
Alerts API endpoints.

Reads from the alerts table populated by backend/alerts/pipeline.py.
Independent of the alerts package so it works whether the server is
started from backend/ or from the project root.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

# DB lives at backend/data/whoboughtmyrep.sqlite — same path as db.py uses.
# Honor FUU_DB_PATH so tests can point this at a tmp file.
_DB_PATH = Path(os.environ.get("FUU_DB_PATH") or Path(__file__).parent.parent / "data" / "whoboughtmyrep.sqlite")

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# Register adapters so date/datetime round-trip cleanly (matches db.py)
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


@contextmanager
def _connect():
    if not _DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Alerts database not initialized. Run: "
                "`python -m backend.db && python -m backend.alerts.seed && "
                "python -m backend.alerts.pipeline` from the project root."
            ),
        )
    conn = sqlite3.connect(_DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_alert(row: sqlite3.Row) -> dict:
    """Shape a row from `alerts JOIN donations JOIN scheduled_votes` for the frontend."""
    try:
        signals = json.loads(row["signals_json"])
    except (TypeError, ValueError):
        signals = {}

    # Compute a relative time string. Prefer updated_at (last reconfirm) so
    # alerts the pipeline keeps refreshing read as fresh; fall back to
    # created_at for legacy rows where updated_at isn't populated yet.
    ts_raw = None
    try:
        ts_raw = row["updated_at"]
    except (IndexError, KeyError):
        ts_raw = None
    if not ts_raw:
        ts_raw = row["created_at"]
    created = ts_raw
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            created = None
    if isinstance(created, datetime):
        # created_at is stored via SQL CURRENT_TIMESTAMP (UTC, naive). Compare
        # against utcnow() so users outside UTC don't see "19 hours ago" on a
        # row that was written 30 seconds back. Strip the tz on `now` so the
        # subtraction works against the naive parsed timestamp.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = now - created
        if delta.days >= 1:
            time_str = f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds >= 3600:
            h = delta.seconds // 3600
            time_str = f"{h} hour{'s' if h != 1 else ''} ago"
        else:
            m = max(1, delta.seconds // 60)
            time_str = f"{m} min{'s' if m != 1 else ''} ago"
    else:
        time_str = "recently"

    actor_type = row["actor_type"]
    actor_id = row["actor_id"]
    return {
        "id": row["id"],
        "actor_type": actor_type,
        "actor_id": actor_id,
        # Legacy field — populated for federal alerts so existing clients keep working.
        "bioguide_id": actor_id if actor_type == "federal" else None,
        "headline": row["headline"],
        "body": row["body"],
        "score": round(row["score"], 3),
        "urgent": bool(row["urgent"]),
        "time": time_str,
        "donation": {
            "pac_name": row["pac_name"],
            "industry": row["industry"],
            "amount": row["amount"],
            "donation_date": row["donation_date"],
        },
        "vote": {
            "bill_number": row["bill_number"],
            "title": row["title"],
            "category": row["category"],
            "scheduled_date": row["scheduled_date"],
        },
        "signals": signals,
    }


@router.get("")
async def list_alerts(
    bioguide_id: Optional[str] = Query(None, description="Federal-only convenience: maps to actor_type=federal,actor_id=<bioguide_id>"),
    actor_type: Optional[str] = Query(None, description="'federal' or 'state'"),
    actor_id: Optional[str] = Query(None, description="Bioguide ID (federal) or Legiscan people_id (state)"),
    urgent_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    include_dismissed: bool = Query(False),
):
    """List recent alerts, sorted by score descending."""
    # Backward-compat: bioguide_id implies federal scope.
    if bioguide_id and not actor_id:
        actor_type = "federal"
        actor_id = bioguide_id

    where = []
    params = []
    if actor_type:
        where.append("a.actor_type = ?")
        params.append(actor_type)
    if actor_id:
        where.append("a.actor_id = ?")
        params.append(actor_id)
    if urgent_only:
        where.append("a.urgent = 1")
    if not include_dismissed:
        where.append("a.dismissed = 0")

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)

    sql = f"""
        SELECT a.id, a.actor_type, a.actor_id, a.headline, a.body, a.score, a.urgent,
               a.signals_json, a.created_at, a.updated_at,
               d.pac_name, d.industry, d.amount, d.donation_date,
               v.bill_number, v.title, v.category, v.scheduled_date
        FROM alerts a
        JOIN donations d ON d.id = a.donation_id
        JOIN scheduled_votes v ON v.id = a.vote_id
        {where_sql}
        ORDER BY a.score DESC
        LIMIT ?
    """

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    alerts = [_row_to_alert(r) for r in rows]
    return {
        "count": len(alerts),
        "filters": {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "urgent_only": urgent_only,
            "include_dismissed": include_dismissed,
        },
        "alerts": alerts,
    }


@router.get("/by-rep/{bioguide_id}")
async def alerts_for_rep(bioguide_id: str, limit: int = Query(20, ge=1, le=100)):
    """Convenience endpoint: alerts for a specific federal legislator."""
    # Pass explicit booleans — calling list_alerts as a plain function would
    # otherwise inherit FastAPI's `Query(False)` defaults, which evaluate
    # truthy and silently filter to urgent-only.
    return await list_alerts(
        bioguide_id=bioguide_id, limit=limit,
        urgent_only=False, include_dismissed=False,
    )


@router.get("/by-actor/{actor_type}/{actor_id}")
async def alerts_for_actor(actor_type: str, actor_id: str, limit: int = Query(20, ge=1, le=100)):
    """Generic convenience endpoint: alerts for any actor (federal or state)."""
    return await list_alerts(
        actor_type=actor_type, actor_id=actor_id, limit=limit,
        urgent_only=False, include_dismissed=False,
    )


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: int):
    """Mark an alert as dismissed so it stops showing up."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE alerts SET dismissed = 1 WHERE id = ?", (alert_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True, "id": alert_id}