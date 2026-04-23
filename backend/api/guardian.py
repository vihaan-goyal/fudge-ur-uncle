"""The Guardian Open Platform API — news article search."""
import re
import httpx
from datetime import datetime, timedelta
from config import GUARDIAN_BASE, GUARDIAN_API_KEY


def _extract_topic(title: str) -> str:
    """
    Pull the meaningful topic out of a verbose congressional hearing title.

    Priority:
      1. After a colon  → "Full Committee Hearing: AI Regulation" → "AI Regulation"
      2. After "on "    → "Hearing on Federal Reserve Policy"     → "Federal Reserve Policy"
      3. After bill comma → "Markup of H.R. 1, the Tax Cuts Act" → "Tax Cuts Act"
      4. Strip boilerplate and return whatever's left
    """
    # Strip "Continuation of … titled '…'" wrapper first
    title = re.sub(
        r"continuation of\s+(the\s+)?(full\s+)?committee hearing on[^,]+,\s*titled\s*['\"]?",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # 1. Topic after colon (must be at least 8 chars so "TBD" etc. don't match)
    m = re.search(r":\s*(.{8,})$", title)
    if m:
        return m.group(1).strip().strip("'\"")

    # 2. Topic after "on [the] ..." (word boundary, at least 8 chars)
    m = re.search(r"\bon\s+(?:the\s+)?(.{8,})$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 3. Bill markup: extract named act after comma
    m = re.search(r"markup of [^,]+,\s*(?:the\s+)?(.+)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 4. Fallback: strip generic words and collapse whitespace
    stripped = re.sub(
        r"\b(full|committee|hearing|markup|executive session|business meeting|oversight|nomination|nominations)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    stripped = " ".join(stripped.split()).strip(" ,.'\"")
    return stripped or title


def _build_query(title: str) -> str:
    topic = _extract_topic(title)
    # Append "US Congress" unless the topic already signals US politics
    if not re.search(r"\b(congress|senate|house|legislation|bill|act)\b", topic, re.IGNORECASE):
        topic = topic + " US Congress"
    # Cap length
    if len(topic) > 100:
        topic = topic[:100].rsplit(" ", 1)[0]
    return topic


async def search_article(query: str) -> dict | None:
    """
    Search for the single most relevant Guardian article.
    Scoped to us-news section; tries last 90 days first, then falls back to all-time.
    Returns {title, url, date, section, snippet} or None if unavailable.
    """
    if not GUARDIAN_API_KEY:
        return None

    clean_q = _build_query(query)
    from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    base_params = {
        "q": clean_q,
        "api-key": GUARDIAN_API_KEY,
        "page-size": 1,
        "order-by": "relevance",
        "show-fields": "trailText",
        "section": "us-news",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # First pass: last 90 days, us-news section
            resp = await client.get(
                f"{GUARDIAN_BASE}/search",
                params={**base_params, "from-date": from_date},
            )
            resp.raise_for_status()
            results = resp.json().get("response", {}).get("results", [])

            # Retry: drop date filter but keep section
            if not results:
                resp2 = await client.get(f"{GUARDIAN_BASE}/search", params=base_params)
                resp2.raise_for_status()
                results = resp2.json().get("response", {}).get("results", [])

            # Last resort: drop section filter too
            if not results:
                fallback = {**base_params}
                fallback.pop("section")
                resp3 = await client.get(f"{GUARDIAN_BASE}/search", params=fallback)
                resp3.raise_for_status()
                results = resp3.json().get("response", {}).get("results", [])

            if not results:
                return None

            r = results[0]
            return {
                "title": r.get("webTitle", ""),
                "url": r.get("webUrl", ""),
                "date": r.get("webPublicationDate", "")[:10],
                "section": r.get("sectionName", ""),
                "snippet": r.get("fields", {}).get("trailText", ""),
            }
    except Exception as e:
        print(f"[guardian] search failed ({e})")
        return None
