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

# Fallback rungs (Track 2 — static ladder). Each rung is a separate static
# fetch attempted only when the prior rung's text is below MIN_USABLE_CHARS,
# so reps with a working .gov site cost nothing extra.
MIN_USABLE_CHARS = 400
WIKIPEDIA_BASE = "https://en.wikipedia.org/wiki/"
BALLOTPEDIA_BASE = "https://ballotpedia.org/"
# Wikipedia asks bots to stay polite; one fetch per rep with a small pause is
# well inside their etiquette guidelines.
WIKI_FETCH_PAUSE_S = 0.5


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


# ---- Fallback ladder helpers (Track 2) ---------------------------

async def _fetch_raw_html(client: httpx.AsyncClient, url: str) -> str:
    """Single-URL static fetch returning the raw HTML body (capped). Empty on
    any failure. Used for noscript/JSON-LD extraction, where the regex strip
    would otherwise destroy the structured fragments we want to keep."""
    try:
        resp = await client.get(url, timeout=PER_PAGE_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype.lower():
            return ""
        return resp.text[:MAX_PAGE_BYTES]
    except Exception:
        return ""


def _collect_jsonld_strings(node) -> list[str]:
    """Walk a JSON-LD blob and collect long-ish string values. SEO-aware sites
    often embed issue blurbs in @graph / description / articleBody fields."""
    out: list[str] = []
    if isinstance(node, dict):
        for v in node.values():
            out.extend(_collect_jsonld_strings(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_collect_jsonld_strings(item))
    elif isinstance(node, str):
        s = node.strip()
        # Drop short ids/urls/labels — they aren't policy text.
        if len(s) > 40 and not s.startswith(("http://", "https://", "@")):
            out.append(s)
    return out


def _extract_jsonld_and_noscript(html_text: str) -> str:
    """Pull readable text from <noscript> blocks and JSON-LD <script> blocks
    that `_strip_html` deliberately discards. SPAs that render via JS often
    ship a server-rendered SEO fallback in these fragments."""
    if not html_text:
        return ""
    parts: list[str] = []

    for m in re.finditer(r"<noscript[^>]*>(.*?)</noscript>",
                          html_text, flags=re.DOTALL | re.IGNORECASE):
        cleaned = _strip_html(m.group(1))
        if cleaned:
            parts.append(cleaned)

    for m in re.finditer(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html_text, flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        strings = _collect_jsonld_strings(data)
        if strings:
            parts.append("\n".join(strings))

    return "\n\n".join(parts).strip()


def _name_to_slug(name: str) -> str:
    """Wikipedia/Ballotpedia URLs replace spaces with underscores. Strip
    trailing periods (initials) so 'John Q. Public' -> 'John_Q._Public'
    is preserved while 'John Public.' -> 'John_Public'."""
    cleaned = (name or "").strip().rstrip(".")
    return cleaned.replace(" ", "_") if cleaned else ""


async def _scrape_with_fallbacks(
    name: str, website: str,
) -> tuple[str, str, list[str]]:
    """Try a ladder of static sources for the rep's policy positions.

    Order: primary site (homepage + issue paths) -> JSON-LD/noscript on
    primary homepage -> Wikipedia -> Ballotpedia. Stops at the first rung
    returning >= MIN_USABLE_CHARS of plain text.

    Returns (text, source_url, attempted). `attempted` lists every rung that
    was tried (whether or not it succeeded) so callers can surface why a
    `scraped: false` happened.
    """
    attempted: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FudgeUrUncle/0.1; civic-research)"}

    # Rung 1: existing path. scrape_site opens its own AsyncClient.
    primary_text = ""
    if website:
        attempted.append("primary")
        primary_text = await scrape_site(website)
        if len(primary_text) >= MIN_USABLE_CHARS:
            return primary_text, website, attempted

    async with httpx.AsyncClient(headers=headers) as client:
        # Rung 2: JSON-LD + noscript on the primary homepage, merged with
        # whatever rung 1 *did* find. A SPA that ships SEO text in JSON-LD
        # combined with a thin scrape often clears the threshold.
        if website:
            attempted.append("noscript")
            raw = await _fetch_raw_html(client, website.rstrip("/"))
            extracted = _extract_jsonld_and_noscript(raw)
            if extracted:
                combined = (primary_text + "\n\n" + extracted) if primary_text else extracted
                combined = combined[:MAX_TEXT_CHARS]
                if len(combined) >= MIN_USABLE_CHARS:
                    return combined, website, attempted

        slug = _name_to_slug(name)
        if slug:
            # Rung 3: Wikipedia. Static, indexed, has "Political positions"
            # sections for most federal reps and many state senators.
            wiki_url = WIKIPEDIA_BASE + slug
            attempted.append("wikipedia")
            await asyncio.sleep(WIKI_FETCH_PAUSE_S)
            wiki_raw = await _fetch_raw_html(client, wiki_url)
            wiki_text = _strip_html(wiki_raw) if wiki_raw else ""
            if len(wiki_text) >= MIN_USABLE_CHARS:
                return wiki_text[:MAX_TEXT_CHARS], wiki_url, attempted

            # Rung 4: Ballotpedia. State reps already had this as rung 1 via
            # `state_sites.derive_website`, so skip when it matches.
            ballot_url = BALLOTPEDIA_BASE + slug
            if ballot_url != website:
                attempted.append("ballotpedia")
                ballot_raw = await _fetch_raw_html(client, ballot_url)
                ballot_text = _strip_html(ballot_raw) if ballot_raw else ""
                if len(ballot_text) >= MIN_USABLE_CHARS:
                    return ballot_text[:MAX_TEXT_CHARS], ballot_url, attempted

    # All rungs exhausted. Return the best we have (might still be < threshold)
    # alongside the attempted list so the caller can decide what to do.
    return primary_text, website or "", attempted


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

    site_text, source_url, attempted = await _scrape_with_fallbacks(name, website)
    if len(site_text) < MIN_USABLE_CHARS:
        print(
            f"[promises] {cache_key}: all rungs failed (attempted={attempted}, "
            f"best={len(site_text)} chars)"
        )
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
            "source_url": source_url or website,
            "source_rung": attempted[-1] if attempted else None,
            "scraped_chars": len(site_text),
        }
        ai_cache.set(cache_key, result)
        print(
            f"[promises] {cache_key}: extracted {len(promises)} promises from "
            f"{len(site_text)} chars via rung={result['source_rung']}"
        )
        return result
    except Exception as e:
        print(f"[promises] {cache_key} failed ({e})")
        return None
