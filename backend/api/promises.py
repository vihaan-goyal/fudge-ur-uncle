"""
Promise scoring: scrape a legislator's official .gov site for stated positions,
then ask GPT-4o-mini to score those promises against their actual voting record.

Two-phase pipeline:
    1. scrape_site(website) -> plain text from homepage + likely issue paths
    2. extract_and_score(text, votes, sponsored) -> list of scored promises

Cached in-process per bioguide_id (same pattern as stance_analysis).
"""
import asyncio
import html as html_lib
import json
import re

import httpx
import openai

from config import OPENAI_API_KEY
from api.congress_gov import format_vote_lines, format_bill_lines
from api import ai_cache

# Common URL paths used by congressional .gov sites for issue/priority pages.
# We try these in addition to the homepage. Most reps use one or two of these.
ISSUE_PATHS = [
    "",
    "/issues",
    "/priorities",
    "/about",
    "/about/issues",
    "/about/priorities",
    "/issues/all",
]

MAX_PAGE_BYTES = 600_000      # cap per page to avoid pulling huge assets
MAX_TEXT_CHARS = 14_000       # cap final text fed to GPT
PER_PAGE_TIMEOUT = 8.0


def _strip_html(html_text: str) -> str:
    """Strip HTML to readable plain text. Regex-based, no BeautifulSoup needed."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"</(p|div|h\d|li|br|tr|section|article|header|footer)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, timeout=PER_PAGE_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype.lower():
            return ""
        body = resp.text[:MAX_PAGE_BYTES]
        return _strip_html(body)
    except Exception:
        return ""


async def scrape_site(website: str) -> str:
    """Fetch the rep's homepage + likely issues pages, return concatenated plain text."""
    if not website:
        return ""
    base = website.rstrip("/")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FudgeUrUncle/0.1; civic-research)"}

    async with httpx.AsyncClient(headers=headers) as client:
        results = await asyncio.gather(
            *[_fetch(client, base + path) for path in ISSUE_PATHS],
            return_exceptions=True,
        )

    seen_chunks: list[str] = []
    seen_total = 0
    for r in results:
        if not isinstance(r, str) or not r:
            continue
        if r in seen_chunks:
            continue
        seen_chunks.append(r)
        seen_total += len(r)
        if seen_total >= MAX_TEXT_CHARS:
            break

    combined = "\n\n---\n\n".join(seen_chunks)
    return combined[:MAX_TEXT_CHARS]


async def get_promises(
    cache_key: str,
    name: str,
    party: str,
    chamber: str,
    website: str,
    votes: list[dict],
    sponsored_bills: list[dict],
) -> dict | None:
    """
    Returns:
      {"promises": [...], "source_url": website, "scraped_chars": N}
    Returns None when OPENAI_API_KEY is missing OR scraping yielded nothing useful.
    """
    if not OPENAI_API_KEY:
        return None

    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    site_text = await scrape_site(website)
    if len(site_text) < 400:
        print(f"[promises] {cache_key}: not enough scraped text ({len(site_text)} chars)")
        return None

    party_label = {"D": "Democrat", "R": "Republican", "I": "Independent"}.get(party, party)

    prompt = (
        f"You are auditing whether {name} ({party_label}, {chamber}) has kept the "
        "policy positions stated on their official website.\n\n"
        "STEP 1 — Read the website text below and identify 4 to 6 distinct policy "
        "positions or commitments this legislator has publicly made (e.g. \"will fight to "
        "lower prescription drug prices\", \"supports stronger border security\"). "
        "Only use positions actually stated in the text — do not invent any.\n\n"
        "STEP 2 — For each position, compare against the votes and sponsored "
        "legislation listed below, and assign a status using these STRICT rules:\n"
        "  - KEPT: at least one substantive bill directly on this topic where the "
        "vote/sponsorship clearly matches the stated position.\n"
        "  - BROKEN: at least one substantive bill directly on this topic where the "
        "vote clearly contradicts the stated position.\n"
        "  - PARTIAL: ONLY when there are multiple directly-relevant substantive "
        "bills with mixed votes (some align, some contradict). Do not use PARTIAL "
        "for a single hedged or tangential vote.\n"
        "  - UNCLEAR: no directly-relevant substantive bills, OR the only matches "
        "are tangential / loosely related / require speculation. When in doubt, use UNCLEAR.\n\n"
        "EVIDENCE RULES:\n"
        "  - Match must be on the bill's actual subject, not a keyword overlap.\n"
        "  - Do not use words like \"may\", \"could\", \"possibly\", \"indirectly\" — "
        "if you'd need them, the match isn't strong enough; use UNCLEAR.\n"
        "  - The vote list below has already been filtered to substantive bills only.\n\n"
        "WEBSITE TEXT:\n"
        f"{site_text}\n\n"
        "SUBSTANTIVE VOTES:\n"
        f"{format_vote_lines(votes)}\n\n"
        "SPONSORED LEGISLATION:\n"
        f"{format_bill_lines(sponsored_bills)}\n\n"
        "Respond with a JSON object: "
        '{"promises": [{"topic": "...", "promise": "...", "status": "KEPT|BROKEN|PARTIAL|UNCLEAR", '
        '"evidence": "cite specific bills with numbers, or say no directly relevant bills"}]}. '
        "No markdown, no preamble."
    )

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        promises = parsed.get("promises") if isinstance(parsed, dict) else None
        if not isinstance(promises, list) or not promises:
            return None

        result = {
            "promises": promises,
            "source_url": website,
            "scraped_chars": len(site_text),
        }
        ai_cache.set(cache_key, result)
        print(f"[promises] {cache_key}: extracted {len(promises)} promises from {len(site_text)} chars")
        return result
    except Exception as e:
        print(f"[promises] {cache_key} failed ({e})")
        return None
