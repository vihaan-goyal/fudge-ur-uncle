"""Events data from Congress.gov Committee Meetings API.

The list endpoint (/v3/committee-meeting) returns only summary stubs with a detail URL.
We do a two-phase fetch: list -> parallel detail requests to get title/date/location.
"""
import asyncio
import httpx
from datetime import datetime, timedelta
from config import CONGRESS_GOV_BASE, DATA_GOV_API_KEY

_cache: dict = {}
_CACHE_TTL = timedelta(minutes=5)

SAMPLE_EVENTS = [
    {"id": 1, "title": "Senate Judiciary Committee Hearing", "date": "Apr 22, 2026",
     "time": "10:00 AM", "location": "Dirksen Senate Office Building 226", "type": "hearing",
     "chamber": "Senate", "congress": 119, "meeting_type": "Hearing",
     "committees": ["Committee on the Judiciary"], "witnesses": [],
     "bills": [], "congress_url": "https://www.congress.gov"},
    {"id": 2, "title": "House Energy and Commerce Markup", "date": "Apr 25, 2026",
     "time": "9:00 AM", "location": "Rayburn House Office Building 2123", "type": "hearing",
     "chamber": "House", "congress": 119, "meeting_type": "Markup",
     "committees": ["Committee on Energy and Commerce"], "witnesses": [],
     "bills": [], "congress_url": "https://www.congress.gov"},
    {"id": 3, "title": "Senate Finance Committee Hearing on Tax Reform", "date": "Apr 28, 2026",
     "time": "10:30 AM", "location": "Dirksen Senate Office Building 215", "type": "hearing",
     "chamber": "Senate", "congress": 119, "meeting_type": "Hearing",
     "committees": ["Committee on Finance"], "witnesses": [],
     "bills": [], "congress_url": "https://www.congress.gov"},
    {"id": 4, "title": "House Armed Services Committee Hearing", "date": "May 1, 2026",
     "time": "2:00 PM", "location": "Rayburn House Office Building 2118", "type": "hearing",
     "chamber": "House", "congress": 119, "meeting_type": "Hearing",
     "committees": ["Committee on Armed Services"], "witnesses": [],
     "bills": [], "congress_url": "https://www.congress.gov"},
]


def _normalize_date(iso_date) -> str:
    """Convert ISO date to display format. Returns 'TBD' on any failure."""
    try:
        dt = datetime.strptime(str(iso_date).split("T")[0], "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except (ValueError, TypeError, AttributeError):
        return "TBD"


def _clean_title(raw: str) -> str:
    """Collapse whitespace and strip control chars from a meeting title.

    Congress.gov sometimes hands back the full agenda blob in the title
    field — embedded `\\r\\n`s and long runs of spaces between numbered
    items. The frontend line-clamps the card display, but normalising here
    keeps the detail screen readable too and avoids paying the noise cost
    in caching/AI-summary keys.
    """
    import re
    if not raw:
        return "Committee Meeting"
    return re.sub(r"\s+", " ", raw).strip() or "Committee Meeting"


_BILL_TYPES = {
    "H.R.": "house-bill",
    "S.": "senate-bill",
    "H.Res.": "house-resolution",
    "S.Res.": "senate-resolution",
    "H.J.Res.": "house-joint-resolution",
    "S.J.Res.": "senate-joint-resolution",
    "H.Con.Res.": "house-concurrent-resolution",
    "S.Con.Res.": "senate-concurrent-resolution",
}


def _bill_page_url(bill_prefix: str, number: str, congress: int) -> str:
    bill_type = _BILL_TYPES.get(bill_prefix)
    if not bill_type or not number:
        return ""
    ordinal = f"{congress}th" if 11 <= congress % 100 <= 13 else {1: "1st", 2: "2nd", 3: "3rd"}.get(congress % 10, f"{congress}th")
    return f"https://www.congress.gov/bill/{ordinal}-congress/{bill_type}/{number}"


def _extract_bills(documents: list, congress: int) -> list:
    """Pull unique bills from meetingDocuments, return up to 5 with their congress.gov page URLs."""
    import re
    seen = set()
    bills = []
    for doc in documents:
        if doc.get("documentType") != "Bills and Resolutions":
            continue
        name = doc.get("name", "")
        # Match bill identifiers at the start: "H.R. 1234" / "S. 56" / "H.Res. 7" etc.
        m = re.match(r'^(H\.R\.|S\.|H\.Res\.|S\.Res\.|H\.J\.Res\.|S\.J\.Res\.|H\.Con\.Res\.|S\.Con\.Res\.)\s*(\d+)', name)
        if not m:
            continue
        prefix, number = m.group(1), m.group(2)
        key = f"{prefix}{number}"
        if key in seen:
            continue
        seen.add(key)
        bill_label = f"{prefix} {number}"
        # Description: everything after the first comma, or fallback to bill number
        parts = name.split(",", 1)
        description = parts[1].strip() if len(parts) > 1 else bill_label
        url = _bill_page_url(prefix, number, congress)
        bills.append({"bill": bill_label, "title": description, "url": url})
        if len(bills) >= 5:
            break
    return bills


def _normalize_detail(raw: dict, idx: int) -> dict:
    meeting = raw.get("committeeMeeting", raw)
    loc = meeting.get("location") or {}
    building = loc.get("building", "")
    room = loc.get("room", "")
    congress = meeting.get("congress", 0)
    chamber = meeting.get("chamber", "")
    raw_type = meeting.get("meetingType") or meeting.get("type", "")
    meeting_type = raw_type.title() if raw_type else "Hearing"
    event_id = meeting.get("eventId", "")

    raw_committees = meeting.get("committees") or []
    committees = [c["name"] for c in raw_committees if isinstance(c, dict) and c.get("name")]

    raw_witnesses = meeting.get("witnesses") or []
    witnesses = [
        {"name": w.get("name", ""), "organization": w.get("organization", "")}
        for w in raw_witnesses if isinstance(w, dict) and w.get("name")
    ]

    bills = _extract_bills(meeting.get("meetingDocuments") or [], congress)

    # Human-readable meeting page on congress.gov
    congress_url = (
        f"https://www.congress.gov/{congress}/meeting/{chamber.lower()}/{event_id}"
        if congress and chamber and event_id else ""
    )

    return {
        "id": idx + 1,
        "title": _clean_title(meeting.get("title", "")),
        "date": _normalize_date(meeting.get("date") or meeting.get("meetingDate", "")),
        "time": meeting.get("time", "TBD"),
        "location": f"{building} {room}".strip() or "U.S. Capitol",
        "type": "hearing",
        "chamber": chamber,
        "meeting_type": meeting_type,
        "congress": congress,
        "committees": committees,
        "witnesses": witnesses,
        "bills": bills,
        "congress_url": congress_url,
    }


async def _fetch_detail(client: httpx.AsyncClient, url: str, idx: int):
    """Fetch one meeting detail URL. Returns None on any error."""
    try:
        resp = await client.get(url, params={"api_key": DATA_GOV_API_KEY, "format": "json"})
        resp.raise_for_status()
        return _normalize_detail(resp.json(), idx)
    except Exception:
        return None


async def fetch_events(limit: int = 20) -> list[dict]:
    global _cache
    if _cache.get("events") and _cache.get("fetched_at"):
        if datetime.now() - _cache["fetched_at"] < _CACHE_TTL:
            return _cache["events"][:limit]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Phase 1: list endpoint — returns stubs with detail URLs
            resp = await client.get(
                f"{CONGRESS_GOV_BASE}/committee-meeting",
                params={"api_key": DATA_GOV_API_KEY, "format": "json", "limit": min(limit, 20)},
            )
            resp.raise_for_status()
            summaries = resp.json().get("committeeMeetings", [])

            if not summaries:
                print("[events] Congress.gov returned empty list, using sample data")
                return SAMPLE_EVENTS[:limit]

            # Phase 2: fetch details in parallel (cap at 10 to stay within rate limits)
            detail_urls = [s["url"] for s in summaries[:10] if "url" in s]
            results = await asyncio.gather(*[
                _fetch_detail(client, url, idx) for idx, url in enumerate(detail_urls)
            ])

        events = [r for r in results if r is not None]
        if not events:
            print("[events] All detail fetches failed, using sample data")
            return SAMPLE_EVENTS[:limit]

        _cache = {"events": events, "fetched_at": datetime.now()}
        print(f"[events] Fetched {len(events)} committee meeting details")
        return events[:limit]
    except Exception as e:
        print(f"[events] Congress.gov unavailable ({e}), using sample data")
        return SAMPLE_EVENTS[:limit]
