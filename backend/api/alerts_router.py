"""
Alerts API endpoints.

Reads from the alerts table populated by backend/alerts/pipeline.py.
Independent of the alerts package so it works whether the server is
started from backend/ or from the project root.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

# DB lives at backend/data/whoboughtmyrep.sqlite — same path as db.py uses
_DB_PATH = Path(__file__).parent.parent / "data" / "whoboughtmyrep.sqlite"

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
    finally:
        conn.close()


def _row_to_alert(row: sqlite3.Row) -> dict:
    """Shape a row from `alerts JOIN donations JOIN scheduled_votes` for the frontend."""
    try:
        signals = json.loads(row["signals_json"])
    except (TypeError, ValueError):
        signals = {}

    # Compute a relative time string so the frontend doesn't have to
    created = row["created_at"]
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            created = None
    if isinstance(created, datetime):
        delta = datetime.now() - created
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

    return {
        "id": row["id"],
        "bioguide_id": row["bioguide_id"],
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
    bioguide_id: Optional[str] = Query(None, description="Filter to a single legislator"),
    urgent_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    include_dismissed: bool = Query(False),
):
    """List recent alerts, sorted by score descending."""
    where = []
    params = []
    if bioguide_id:
        where.append("a.bioguide_id = ?")
        params.append(bioguide_id)
    if urgent_only:
        where.append("a.urgent = 1")
    if not include_dismissed:
        where.append("a.dismissed = 0")

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)

    sql = f"""
        SELECT a.id, a.bioguide_id, a.headline, a.body, a.score, a.urgent,
               a.signals_json, a.created_at,
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
            "bioguide_id": bioguide_id,
            "urgent_only": urgent_only,
            "include_dismissed": include_dismissed,
        },
        "alerts": alerts,
    }


@router.get("/by-rep/{bioguide_id}")
async def alerts_for_rep(bioguide_id: str, limit: int = Query(20, ge=1, le=100)):
    """Convenience endpoint: alerts for a specific legislator."""
    return await list_alerts(bioguide_id=bioguide_id, limit=limit)


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: int):
    """Mark an alert as dismissed so it stops showing up."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE alerts SET dismissed = 1 WHERE id = ?", (alert_id,)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True, "id": alert_id}