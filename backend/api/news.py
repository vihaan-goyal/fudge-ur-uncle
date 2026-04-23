"""NewsAPI.org — US-focused news article search for congressional committee meetings."""
import re
import httpx
from datetime import datetime, timedelta
from config import NEWSAPI_BASE, NEWSAPI_KEY


def _extract_topic(title: str) -> str:
    """Pull the meaningful topic out of a verbose congressional hearing title."""
    # Strip "Continuation of … titled '…'" wrapper
    title = re.sub(
        r"continuation of\s+(the\s+)?(full\s+)?committee hearing on[^,]+,\s*titled\s*['\"]?",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # Topic after colon: "Full Committee Hearing: AI Regulation" → "AI Regulation"
    m = re.search(r":\s*(.{8,})$", title)
    if m:
        return m.group(1).strip().strip("'\"")

    # Topic after "on [the]": "Hearing on Federal Reserve Policy" → "Federal Reserve Policy"
    m = re.search(r"\bon\s+(?:the\s+)?(.{8,})$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Markup of bill: "Markup of H.R. 1, the Energy Price Act" → "Energy Price Act"
    m = re.search(r"markup of [^,]+,\s*(?:the\s+)?(.+)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Fallback: strip boilerplate words
    stripped = re.sub(
        r"\b(full|committee|hearing|markup|executive session|business meeting|oversight|nomination|nominations)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return " ".join(stripped.split()).strip(" ,.'\"") or title


def _build_query(title: str) -> str:
    topic = _extract_topic(title)
    if not re.search(r"\b(congress|senate|house|legislation|bill|act)\b", topic, re.IGNORECASE):
        topic = topic + " Congress"
    if len(topic) > 100:
        topic = topic[:100].rsplit(" ", 1)[0]
    return topic


async def search_article(query: str) -> dict | None:
    """
    Search NewsAPI.org for the most relevant article about a committee hearing.
    Tries last 30 days first; falls back to all-time if no results.
    Returns {title, url, date, section, snippet} or None.
    """
    if not NEWSAPI_KEY:
        return None

    clean_q = _build_query(query)
    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    base_params = {
        "q": clean_q,
        "apiKey": NEWSAPI_KEY,
        "pageSize": 1,
        "sortBy": "relevance",
        "language": "en",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # First pass: last 30 days
            resp = await client.get(
                f"{NEWSAPI_BASE}/everything",
                params={**base_params, "from": from_date},
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])

            # Fallback: no date filter
            if not articles:
                resp2 = await client.get(f"{NEWSAPI_BASE}/everything", params=base_params)
                resp2.raise_for_status()
                articles = resp2.json().get("articles", [])

            if not articles:
                return None

            a = articles[0]
            return {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "date": (a.get("publishedAt") or "")[:10],
                "section": (a.get("source") or {}).get("name", ""),
                "snippet": a.get("description", ""),
            }
    except Exception as e:
        print(f"[news] NewsAPI search failed ({e})")
        return None
