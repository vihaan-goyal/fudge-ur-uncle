"""Regression tests for backend/alerts/state_categories.py.

Two things this file locks in:

1. Newly-added keyword patterns (May 2026 expansion) keep matching the
   real-world federal + state titles that motivated them. Drift on any
   of these would silently regress the alert pool.

2. Procedural / generic titles that should stay uncategorized do — most
   importantly, the "An Act Concerning The State Building Code" case
   that originally drove us to drop the description-fallback path. If
   that one starts matching `education` or anything else, the title-only
   discipline is leaking.

Categories here intentionally line up with `industry_map.py`. New patterns
should generally not need new categories — if a bill genuinely doesn't fit
the existing 13, leaving it uncategorized is the right call.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from backend.alerts.state_categories import categorize


@pytest.mark.parametrize("title,expected", [
    # --- Pre-existing patterns: smoke check that the basics still work.
    ("An Act Concerning Climate Change Goals.", "environment"),
    ("An Act Concerning Prescription Drug Pricing.", "healthcare"),
    ("An Act Concerning Property Tax Relief.", "economy"),
    ("An Act Concerning Veterans' Benefits.", "defense"),
    ("An Act Concerning Affordable Housing.", "housing"),
    ("An Act Concerning Charter Schools.", "education"),
    ("An Act Concerning Sanctuary Cities.", "immigration"),
    ("An Act Concerning Firearms Background Checks.", "firearms"),
    ("An Act Concerning Absentee Ballots.", "elections"),

    # --- Environment expansion
    ("Emergency Wildfire Fighting Technology Act of 2025.", "environment"),
    ("An Act Concerning Invasive Species Management.", "environment"),
    ("An Act Concerning The Safety Of Energy Generation Sources And Energy Storage Systems.", "environment"),
    ("An Act Concerning The Tire Stewardship Program.", "environment"),
    ("An Act Concerning The Sewage Right-to-know Act And Requiring A Report Concerning Well Contamination Protocols.", "environment"),

    # --- Healthcare expansion
    ("Chronic Disease Flexible Coverage Act.", "healthcare"),
    ("Protect Our Seniors Act.", "healthcare"),
    ("An Act Concerning Senior Citizens.", "healthcare"),
    ("An Act Concerning Elderly Caregivers.", "healthcare"),
    ("An Act Concerning Electronic Nicotine Delivery System And Vapor Product Dealers.", "healthcare"),
    ("An Act Concerning The Statute Of Limitation For Injury Caused By Fraud In The Provision Of Fertility Care And Treatment.", "healthcare"),
    ("An Act Concerning Dentistry.", "healthcare"),
    ("An Act Concerning Social Work Licensure.", "healthcare"),

    # --- Economy expansion
    ("An Act Concerning Insurance Regulation In The State.", "economy"),
    ("An Act Concerning Commercial Financing.", "economy"),
    ("Securities and Exchange Commission Real Estate Leasing Authority Revocation Act.", "economy"),
    ("Chinese Currency Accountability Act of 2025.", "economy"),
    ("China Trade Relations Act of 2025.", "economy"),
    ("An Act Authorizing The Deferral Of A Property Revaluation.", "economy"),
    ("An Act Concerning Differential Mill Rates.", "economy"),
    ("Legislative Line Item Veto Act of 2025.", "economy"),

    # --- Defense expansion
    ("NATO Edge Act.", "defense"),

    # --- Infrastructure expansion
    ("Postal Service Transparency and Review Act.", "infrastructure"),
    ("An Act Expanding Permissible Uses For Town Aid Road Grant Funds.", "infrastructure"),

    # --- Technology expansion
    ("An Act Concerning Breaches Of Security Involving Electronic Personal Information.", "technology"),
    ("An Act Redefining 'Executive Branch Agency' For Purposes Of Data Governance.", "technology"),
    ("Commercial Remote Sensing Amendment Act of 2025.", "technology"),

    # --- Labor expansion
    ("An Act Implementing The Recommendations Of The Labor Department.", "labor"),
    ("No Dollars to Uyghur Forced Labor Act.", "labor"),

    # --- Housing expansion
    ("An Act Concerning The Purchase Of Residential Property By Private Equity Entities.", "housing"),
    ("An Act Authorizing Municipalities To Enforce Certain Blight Regulations Without Providing Notice Or An Opportunity To Remediate.", "housing"),
    ("An Act Concerning Mobile Manufactured Homes And Mobile Manufactured Home Parks.", "housing"),
    ("An Act Allowing Long-term Rental Of Bedrooms In A Single-family Home As Of Right.", "housing"),
    ("An Act Concerning Homeowners Insurance Disclosure.", "housing"),
    ("An Act Concerning The Uniform Relocation Assistance Act.", "housing"),
    ("An Act Concerning Historic Districts And Historic Preservation.", "housing"),

    # --- Elections expansion
    ("An Act Concerning Faithful Presidential Electors.", "elections"),
])
def test_categorize_positive(title, expected):
    assert categorize(title) == expected, (
        f"{title!r} got {categorize(title)!r}, expected {expected!r}"
    )


@pytest.mark.parametrize("title", [
    # The original anchor: title-only discipline must keep "Building Code"
    # out of `education`. Pre-cleanup, the description fallback got it
    # tagged because the policy summary mentioned schools.
    "An Act Concerning The State Building Code.",

    # Generic / procedural titles. Without a clear policy signal these
    # should drop out of the alert pipeline rather than getting tagged
    # arbitrarily.
    "An Act Concerning Planning And Development.",
    "An Act Conveying A Parcel Of State Land To The Town Of North Canaan.",
    "An Act Implementing The Recommendations Of The Majority Leader's Roundtable.",
    "An Act Requiring Annual State Agency Performance Plans.",
    "An Act Implementing The Recommendations Of The Office Of State Ethics For Revisions To The State Codes Of Ethics.",
    "An Act Concerning The Publication Of Municipal Legal Notices.",
    "An Act Implementing The Recommendations Of The Freedom Of Information Commission For Revisions To The Freedom Of Information Act.",

    # Empty / no-input.
    "",
])
def test_categorize_stays_none(title):
    assert categorize(title) is None, (
        f"{title!r} unexpectedly tagged {categorize(title)!r}; should be None"
    )


@pytest.mark.parametrize("title,expected", [
    # Bare "energy" was deliberately excluded — only specific energy
    # contexts should match. This pair regression-tests the choice.
    ("Strategic Energy Coalition Act.", None),  # no specific energy term
    ("An Act Concerning Renewable Energy Procurement.", "environment"),

    # `\bsenior\b` would catch "senior partner" — only `\bseniors\b`
    # (plural) and `\bsenior citizens?\b` are allowed.
    ("An Act Concerning Senior Partner Disclosures.", None),
    ("An Act Concerning Seniors.", "healthcare"),

    # `\bdental\b` matches "dental" but `\bdentist` covers dentistry too.
    ("An Act Concerning Dental Coverage.", "healthcare"),
    ("An Act Concerning Dentistry.", "healthcare"),
])
def test_categorize_boundary_cases(title, expected):
    assert categorize(title) == expected, (
        f"{title!r} got {categorize(title)!r}, expected {expected!r}"
    )


# ---------- AI fallback ----------
#
# These tests exercise the wiring around ai_categorize, not the LLM itself.
# They stub the OpenAI client + ai_cache so the path runs with no API key
# and confirm: regex hits don't invoke AI, regex misses do, and recovered
# categories flow through into the ingester stats.


@pytest.fixture
def stub_ai_cache(app):
    """Use an in-memory dict instead of SQLite for cat:* keys.

    Depends on `app` so the conftest fixture chain sets FUU_DB_PATH before
    we (transitively) import `api.ai_cache` — that module eagerly loads
    `db` and would otherwise bind DB_PATH to the prod path mid-session,
    breaking later ingester tests.
    """
    store: dict = {}

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value, ttl_hours=168):
        store[key] = value

    with patch("api.ai_cache.get", side_effect=fake_get), \
         patch("api.ai_cache.set", side_effect=fake_set):
        yield store


def _make_openai_stub(reply: str):
    """Return an async stub of openai.AsyncOpenAI.chat.completions.create."""
    class _Msg:
        content = reply
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]

    async def _create(*_args, **_kwargs):
        return _Resp()

    class _Completions:
        create = staticmethod(_create)
    class _Chat:
        completions = _Completions()
    class _Client:
        def __init__(self, *_args, **_kwargs):
            self.chat = _Chat()

    return _Client


def test_ai_categorize_returns_none_without_key(stub_ai_cache):
    """No API key -> behaviour identical to today (returns None)."""
    import asyncio
    from backend.alerts import state_categories

    with patch.object(state_categories, "__name__", state_categories.__name__):
        # Patch config.OPENAI_API_KEY at the module attribute lookup site.
        import config
        with patch.object(config, "OPENAI_API_KEY", ""):
            result = asyncio.run(state_categories.ai_categorize("Some Random Title"))
    assert result is None


def test_ai_categorize_maps_valid_category(stub_ai_cache):
    """gpt-4o-mini returns "healthcare" -> we trust it and cache."""
    import asyncio
    import config
    from backend.alerts import state_categories

    stub_client = _make_openai_stub("healthcare")
    with patch.object(config, "OPENAI_API_KEY", "sk-test"), \
         patch("openai.AsyncOpenAI", stub_client):
        result = asyncio.run(state_categories.ai_categorize(
            "An Act Concerning Pharmacy Benefit Managers",
            "Regulates PBM reimbursement practices.",
        ))
    assert result == "healthcare"
    # Verify it cached the result.
    cache_key = state_categories._ai_cache_key(
        "An Act Concerning Pharmacy Benefit Managers",
        "Regulates PBM reimbursement practices.",
    )
    assert stub_ai_cache[cache_key] == "healthcare"


def test_ai_categorize_none_sentinel_cached(stub_ai_cache):
    """When gpt returns 'none', we cache the literal 'none' so we don't
    pay for the same bill on the next ingest pass."""
    import asyncio
    import config
    from backend.alerts import state_categories

    stub_client = _make_openai_stub("none")
    with patch.object(config, "OPENAI_API_KEY", "sk-test"), \
         patch("openai.AsyncOpenAI", stub_client):
        result = asyncio.run(state_categories.ai_categorize(
            "An Act Conveying State Land In Smithville",
        ))
    assert result is None
    cache_key = state_categories._ai_cache_key("An Act Conveying State Land In Smithville", "")
    assert stub_ai_cache[cache_key] == "none"


def test_ai_categorize_garbage_reply_treated_as_none(stub_ai_cache):
    """Model hallucinates something off-list -> we drop it rather than
    poisoning the alert pool with a made-up category."""
    import asyncio
    import config
    from backend.alerts import state_categories

    stub_client = _make_openai_stub("transportation")  # not in the 13-cat list
    with patch.object(config, "OPENAI_API_KEY", "sk-test"), \
         patch("openai.AsyncOpenAI", stub_client):
        result = asyncio.run(state_categories.ai_categorize("An Act Concerning Mopeds"))
    assert result is None


def test_ai_categorize_cache_hit_skips_openai(stub_ai_cache):
    """If the cache already has a result, we don't hit OpenAI at all."""
    import asyncio
    import config
    from backend.alerts import state_categories

    title = "An Act Concerning Cookie Privacy"
    key = state_categories._ai_cache_key(title, "")
    stub_ai_cache[key] = "technology"

    called = {"n": 0}

    class _BoomClient:
        def __init__(self, *_a, **_kw):
            called["n"] += 1
            raise AssertionError("should not be called on cache hit")

    with patch.object(config, "OPENAI_API_KEY", "sk-test"), \
         patch("openai.AsyncOpenAI", _BoomClient):
        result = asyncio.run(state_categories.ai_categorize(title))

    assert result == "technology"
    assert called["n"] == 0


# ---------- Ingester wiring ----------
#
# The federal-ingest tests already cover the regex+skip path. These add the
# AI-recovery path: when categorize() returns None and ai_categorize() returns
# a real category, the bill gets written and ai_recovered increments.


def test_ingester_uses_ai_fallback_on_regex_miss(app):
    """A title the regex can't read but the AI can recover should write
    a row and increment ai_recovered."""
    import asyncio
    from datetime import date
    from unittest.mock import patch
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    with connect() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM scheduled_votes")
        conn.commit()

    today = date.today()
    fake_bills = [{
        "bill_id": "hr-9000-119",
        # No category keyword in the title; only AI could decide this is healthcare.
        # Avoid "bridge"/"drug"/"medicare" etc. — they all hit existing regex
        # patterns. This title uses words that are not in any keyword list.
        "number": "H.R.9000",
        "title": "Strategic Synergy Modernization Resilience Act",
        "status": "Reported by Committee",
        "status_date": today.isoformat(),
        "chamber": "house",
        "congress": 119,
    }]

    async def fake_get_active_bills(**_kw):
        return fake_bills

    async def fake_ai_categorize(title, description=""):
        return "healthcare"

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills), \
         patch("backend.alerts.ingest_federal_votes.ai_categorize", new=fake_ai_categorize):
        stats = asyncio.run(ingest_federal_votes())

    assert stats["rows_inserted"] == 1
    assert stats["ai_recovered"] == 1
    assert stats["uncategorized_skipped"] == 0

    with connect() as conn:
        row = conn.execute(
            "SELECT category FROM scheduled_votes WHERE bill_number = 'H.R.9000'"
        ).fetchone()
    assert row["category"] == "healthcare"


def test_ingester_ai_miss_still_skips(app):
    """When AI also returns None, the bill is dropped just like before
    and uncategorized_skipped increments."""
    import asyncio
    from datetime import date
    from unittest.mock import patch
    from db import connect
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    with connect() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM scheduled_votes")
        conn.commit()

    today = date.today()
    fake_bills = [{
        "bill_id": "hr-1-119",
        "number": "H.R.1",
        "title": "Procedural Renaming Act",
        "status": "Reported by Committee",
        "status_date": today.isoformat(),
        "chamber": "house",
        "congress": 119,
    }]

    async def fake_get_active_bills(**_kw):
        return fake_bills

    async def fake_ai_categorize(title, description=""):
        return None

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills), \
         patch("backend.alerts.ingest_federal_votes.ai_categorize", new=fake_ai_categorize):
        stats = asyncio.run(ingest_federal_votes())

    assert stats["rows_inserted"] == 0
    assert stats["ai_recovered"] == 0
    assert stats["uncategorized_skipped"] == 1


def test_ingester_regex_hit_skips_ai_entirely(app):
    """When the regex matches, ai_categorize must not be invoked — both for
    speed and to keep the API budget honest."""
    import asyncio
    from datetime import date
    from unittest.mock import patch
    from backend.alerts.ingest_federal_votes import ingest_federal_votes

    with __import__("db").connect() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM scheduled_votes")
        conn.commit()

    today = date.today()
    fake_bills = [{
        "bill_id": "s-872-119",
        "number": "S.872",
        "title": "Prescription Drug Pricing Reform Act",  # clear healthcare hit
        "status": "Reported by Committee",
        "status_date": today.isoformat(),
        "chamber": "senate",
        "congress": 119,
    }]

    called = {"n": 0}

    async def fake_ai_categorize(*_a, **_kw):
        called["n"] += 1
        return "economy"  # would be wrong; assertion below proves it never ran

    async def fake_get_active_bills(**_kw):
        return fake_bills

    with patch("api.congress_gov.get_active_bills", new=fake_get_active_bills), \
         patch("backend.alerts.ingest_federal_votes.ai_categorize", new=fake_ai_categorize):
        stats = asyncio.run(ingest_federal_votes())

    assert called["n"] == 0, "regex hit should short-circuit before AI fallback"
    assert stats["rows_inserted"] == 1
    assert stats["ai_recovered"] == 0
