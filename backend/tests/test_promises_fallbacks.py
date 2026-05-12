"""Tests for the static fallback ladder in `backend/api/promises.py`.

Covers:
1. JSON-LD / noscript extraction recovers content from SPA shells that the
   plain-HTML stripper would drop.
2. `_scrape_with_fallbacks` walks primary -> noscript -> Wikipedia ->
   Ballotpedia, stops at the first rung clearing MIN_USABLE_CHARS, and
   reports the `attempted` list honestly.

Network is stubbed via httpx.MockTransport so the suite never reaches out.
"""
import sys
from pathlib import Path

import httpx
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _make_responder(routes: dict[str, tuple[int, str]]):
    """Build an httpx.MockTransport handler that returns canned responses.

    Routes are keyed by URL prefix (longest match wins) so callers can write
    `https://example.com/issues` once and have all `/issues/*` paths hit it.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, (status, body) in sorted(routes.items(), key=lambda kv: -len(kv[0])):
            if url.startswith(prefix):
                return httpx.Response(
                    status,
                    text=body,
                    headers={"content-type": "text/html; charset=utf-8"},
                )
        return httpx.Response(404, text="", headers={"content-type": "text/html"})
    return handler


# ---------- _extract_jsonld_and_noscript ----------


def test_extract_jsonld_pulls_long_strings():
    """JSON-LD blobs often hold blurbs in description/articleBody. Recover them."""
    from api.promises import _extract_jsonld_and_noscript

    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Jane Q. Senator",
        "description": "Senator Smith has championed affordable housing reform and pushed for a 40-hour work week guarantee for state employees across all sectors.",
        "knowsAbout": [
          "Affordable housing and tenant rights for the working class in urban areas",
          "url:https://example.com"
        ]
      }
      </script>
    </head><body><div>App is loading...</div></body></html>
    """
    out = _extract_jsonld_and_noscript(html)
    assert "affordable housing" in out.lower()
    assert "work week" in out.lower()
    # URLs and the short "name" field shouldn't be included.
    assert "https://example.com" not in out
    assert "Jane Q. Senator" not in out  # too short for the policy-text floor


def test_extract_noscript_block_returns_inner_text():
    from api.promises import _extract_jsonld_and_noscript

    html = """
    <html><body>
      <div>shell</div>
      <noscript>
        <h1>Climate Policy</h1>
        <p>Senator advocates for net-zero emissions across the power sector by 2035, with strong enforcement on industrial polluters.</p>
      </noscript>
    </body></html>
    """
    out = _extract_jsonld_and_noscript(html)
    assert "Climate Policy" in out
    assert "net-zero" in out


def test_extract_returns_empty_for_plain_html():
    """No JSON-LD or noscript -> no fallback text. Critical: the stripper
    handles plain HTML; the JSON-LD path must not double-extract everything."""
    from api.promises import _extract_jsonld_and_noscript

    html = "<html><body><h1>Bio</h1><p>Some bio text.</p></body></html>"
    assert _extract_jsonld_and_noscript(html) == ""


# ---------- _name_to_slug ----------


@pytest.mark.parametrize("name,expected", [
    ("Jane Doe", "Jane_Doe"),
    ("Martin M. Looney", "Martin_M._Looney"),
    ("John Q. Public.", "John_Q._Public"),  # trailing period stripped
    ("", ""),
    (None, ""),
])
def test_name_to_slug(name, expected):
    from api.promises import _name_to_slug
    assert _name_to_slug(name) == expected


# ---------- _scrape_with_fallbacks ----------


@pytest.fixture
def patch_httpx(monkeypatch):
    """Replace httpx.AsyncClient with one that uses a MockTransport.

    Reuses the existing `_fetch` / `_fetch_raw_html` callers which construct
    their own AsyncClient inside the function — patching the constructor
    routes every fetch through our handler.
    """
    def _install(routes: dict[str, tuple[int, str]]):
        handler = _make_responder(routes)
        transport = httpx.MockTransport(handler)

        original = httpx.AsyncClient

        def _factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return _install


def test_primary_site_short_circuits_when_text_is_enough(patch_httpx):
    """If the rep's .gov has plenty of issue text, no fallback fires."""
    import asyncio
    from api import promises

    long_body = "<html><body><h1>Issues</h1>" + ("<p>I support affordable housing reform and a stronger minimum wage.</p>" * 30) + "</body></html>"
    patch_httpx({
        "https://senator.example.gov/": (200, long_body),
    })

    text, source_url, attempted = asyncio.run(
        promises._scrape_with_fallbacks("Jane Senator", "https://senator.example.gov")
    )

    assert "affordable housing" in text.lower()
    assert source_url == "https://senator.example.gov"
    assert attempted == ["primary"]


def test_falls_through_to_wikipedia_when_primary_thin(patch_httpx):
    """JS-rendered primary returns nothing useful; Wikipedia is static and
    fills the gap."""
    import asyncio
    from api import promises

    # Primary is a typical SPA shell with no real content + no JSON-LD/noscript.
    spa_shell = '<html><body><div id="root"></div></body></html>'
    wiki_body = (
        "<html><body>"
        "<h1>Jane Senator</h1>"
        + ("<p>Jane Senator has consistently supported climate legislation, "
           "voted in favor of expanded paid family leave, and championed "
           "affordable housing initiatives in the state senate.</p>" * 10)
        + "</body></html>"
    )

    patch_httpx({
        "https://senator.example.gov/": (200, spa_shell),
        "https://en.wikipedia.org/wiki/Jane_Senator": (200, wiki_body),
    })

    text, source_url, attempted = asyncio.run(
        promises._scrape_with_fallbacks("Jane Senator", "https://senator.example.gov")
    )

    assert source_url == "https://en.wikipedia.org/wiki/Jane_Senator"
    # 'primary' is still in attempted — we tried it before falling back.
    assert "primary" in attempted
    assert "wikipedia" in attempted
    assert "climate legislation" in text.lower()


def test_returns_thin_text_and_full_attempted_when_all_fail(patch_httpx):
    """Honest failure: every rung tried, all under threshold. Caller decides
    what to surface; we don't lie about which rungs were attempted."""
    import asyncio
    from api import promises

    short = "<html><body><p>Hi.</p></body></html>"
    patch_httpx({
        "https://senator.example.gov/": (200, short),
        "https://en.wikipedia.org/wiki/Jane_Senator": (200, short),
        "https://ballotpedia.org/Jane_Senator": (200, short),
    })

    text, source_url, attempted = asyncio.run(
        promises._scrape_with_fallbacks("Jane Senator", "https://senator.example.gov")
    )

    # Below threshold means the caller returns None / scraped: false. We just
    # verify the ladder walked the full set.
    assert len(text) < promises.MIN_USABLE_CHARS
    assert attempted == ["primary", "noscript", "wikipedia", "ballotpedia"]


def test_skips_ballotpedia_when_already_primary(patch_httpx):
    """State reps already get Ballotpedia as their primary site (via
    state_sites.derive_website). Don't refetch it as rung 4."""
    import asyncio
    from api import promises

    short = "<html><body><p>Stub.</p></body></html>"
    patch_httpx({
        "https://ballotpedia.org/Jane_Rep": (200, short),
        "https://en.wikipedia.org/wiki/Jane_Rep": (200, short),
    })

    text, source_url, attempted = asyncio.run(
        promises._scrape_with_fallbacks("Jane Rep", "https://ballotpedia.org/Jane_Rep")
    )

    assert "ballotpedia" not in attempted
    # The other rungs were still walked.
    assert attempted == ["primary", "noscript", "wikipedia"]
