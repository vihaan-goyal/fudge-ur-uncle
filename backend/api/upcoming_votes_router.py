"""Upcoming-votes API endpoint.

Reads `scheduled_votes` directly so the Dashboard doesn't have to dedupe
`/api/alerts` rows (each donation×vote pair produces a row, so the same
bill repeats per donor industry).

Optional auth: when a valid bearer token is present and the user has stored
`issues`, the endpoint defaults `categories` to that list. Explicit
`?categories=` query overrides.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_user_optional

_DB_PATH = Path(
    os.environ.get("FUU_DB_PATH")
    or Path(__file__).parent.parent / "data" / "whoboughtmyrep.sqlite"
)

router = APIRouter(prefix="/api/upcoming-votes", tags=["upcoming-votes"])

# Mirrors CATEGORY_KEYWORDS in backend/alerts/state_categories.py. Kept as a
# literal set so this module doesn't need to import the alerts package.
VALID_CATEGORIES = {
    "environment", "healthcare", "economy", "defense", "infrastructure",
    "technology", "labor", "agriculture", "housing", "education",
    "immigration", "firearms", "elections", "foreign_policy",
}


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
                "`python -m backend.db` from the project root."
            ),
        )
    conn = sqlite3.connect(_DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _parse_categories(raw: Optional[str]) -> Optional[list]:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    bad = [p for p in parts if p not in VALID_CATEGORIES]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {bad[0]}",
        )
    return parts or None


@router.get("")
async def list_upcoming_votes(
    state: Optional[str] = Query(None, min_length=2, max_length=2),
    categories: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Upcoming votes ordered by scheduled date.

    - `state`: 2-letter code. Federal rows always included; state rows narrowed
      to the requested state. Omit to get all states + federal.
    - `categories`: comma-separated category keys (e.g. `healthcare,housing`).
      Validated against the 14-key allowlist.
    - When the request is authenticated and `categories` is omitted, the user's
      stored `issues` (intersected with the allowlist) are used as the filter.
    """
    cat_list = _parse_categories(categories)

    # Personalization: if no explicit categories AND user has issues, default
    # to user's issues intersected with the valid set. Unknown stored values
    # (legacy display strings) are dropped silently.
    if cat_list is None and current_user and current_user.get("issues"):
        intersected = [c for c in current_user["issues"] if c in VALID_CATEGORIES]
        if intersected:
            cat_list = intersected

    where = []
    params: list = []
    if state:
        # Federal (state_code IS NULL) always returned; state side narrowed.
        where.append("(state_code IS NULL OR state_code = ?)")
        params.append(state.upper())
    if cat_list:
        placeholders = ",".join("?" * len(cat_list))
        where.append(f"category IN ({placeholders})")
        params.extend(cat_list)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    sql = f"""
        SELECT id, jurisdiction, state_code, bill_number, title, category,
               scheduled_date, chamber
          FROM scheduled_votes
          {where_sql}
         ORDER BY scheduled_date ASC, created_at DESC
         LIMIT ?
    """

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    today = date.today()
    votes = []
    for r in rows:
        sched = r["scheduled_date"]
        if isinstance(sched, str):
            sched = date.fromisoformat(sched)
        votes.append({
            "id": r["id"],
            "jurisdiction": r["jurisdiction"],
            "state_code": r["state_code"],
            "bill_number": r["bill_number"],
            "title": r["title"],
            "category": r["category"],
            "scheduled_date": sched.isoformat() if sched else None,
            "chamber": r["chamber"],
            "days_until": (sched - today).days if sched else None,
        })

    return {
        "count": len(votes),
        "filters": {
            "state": state.upper() if state else None,
            "categories": cat_list,
            "personalized": cat_list is not None and categories is None,
        },
        "votes": votes,
    }
