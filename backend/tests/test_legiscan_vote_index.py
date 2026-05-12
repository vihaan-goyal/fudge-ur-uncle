"""Tests for the per-state Legiscan vote index.

Locks in two contracts:

1. `build_state_vote_index` walks the masterlist + bill + roll-call endpoints
   and produces a {people_id (str) -> [vote rows]} reverse index. Cached under
   `legiscan:vote_index:{state}` with 24h TTL.

2. `get_legislator_votes` reads from that index first and only falls back to
   the sponsored-only probe when the index is absent. The fast path is what
   closes the "empty backbencher" gap — non-sponsors who actually voted on
   recent bills must now show votes.

Stubs `legiscan._call` so the suite never touches the live API. The fixtures
depend on `app` so FUU_DB_PATH is set before `api.ai_cache` is imported
(otherwise it captures the prod DB path mid-session).
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _canned_call(payloads):
    """Build an async stub for `legiscan._call` that dispatches by `op`.

    `payloads` maps op-name -> dict-or-callable. Callables receive the kwargs.
    Unknown ops raise so the test surfaces misuse instead of silently passing.
    """
    async def _call(op, **kwargs):
        if op not in payloads:
            raise AssertionError(f"unexpected _call op={op} kwargs={kwargs}")
        target = payloads[op]
        if callable(target):
            return target(**kwargs)
        return target
    return _call


@pytest.fixture
def stub_ai_cache(app):
    """In-memory cache shared by build + read paths. Depends on `app` so
    FUU_DB_PATH is set before api.ai_cache is imported (same trick as
    test_state_categories.py)."""
    store: dict = {}

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value, ttl_hours=168):
        store[key] = value

    with patch("api.ai_cache.get", side_effect=fake_get), \
         patch("api.ai_cache.set", side_effect=fake_set):
        yield store


@pytest.fixture
def with_legiscan_key():
    """Force LEGISCAN_API_KEY so the early-exit path doesn't short-circuit."""
    import config
    with patch.object(config, "LEGISCAN_API_KEY", "test-key"):
        # legiscan.py reads from `config` at module top, so also patch there.
        from api import legiscan
        with patch.object(legiscan, "LEGISCAN_API_KEY", "test-key"):
            yield


# ---------- build_state_vote_index ----------


def test_build_index_returns_empty_without_key(stub_ai_cache):
    """No API key -> no fetch, no cache write, return {}."""
    import asyncio
    import config
    from api import legiscan

    with patch.object(config, "LEGISCAN_API_KEY", ""), \
         patch.object(legiscan, "LEGISCAN_API_KEY", ""):
        result = asyncio.run(legiscan.build_state_vote_index("CT"))

    assert result == {}
    assert "legiscan:vote_index:CT" not in stub_ai_cache


def test_build_index_writes_reverse_index(stub_ai_cache, with_legiscan_key):
    """Two bills, one roll call each, three members per call. The resulting
    index should key by people_id (as str, for JSON round-tripping) with each
    member's votes sorted newest-first across both calls."""
    import asyncio
    from api import legiscan

    payloads = {
        "getSessionList": {"sessions": [{"session_id": 9001}]},
        "getMasterList": {
            "masterlist": {
                "session": {"session_id": 9001},
                "1": {"bill_id": 101, "number": "HB-1", "title": "Clean Energy Act",
                       "last_action_date": "2026-05-10"},
                "2": {"bill_id": 102, "number": "SB-2", "title": "Prescription Drug Pricing Act",
                       "last_action_date": "2026-05-08"},
                "3": {"bill_id": 103, "number": "HB-3", "title": "Sidewalk Repair Act",
                       "last_action_date": "2026-04-01"},
            },
        },
        "getBill": lambda id, **_kw: {
            "bill": {
                101: {
                    "title": "Clean Energy Act",
                    "votes": [{"roll_call_id": 5001, "date": "2026-05-11", "chamber": "H"}],
                },
                102: {
                    "title": "Prescription Drug Pricing Act",
                    "votes": [{"roll_call_id": 5002, "date": "2026-05-09", "chamber": "S"}],
                },
                103: {
                    "title": "Sidewalk Repair Act",
                    # No roll call yet — should be skipped silently.
                    "votes": [],
                },
            }[id],
        },
        "getRollCall": lambda id, **_kw: {
            "roll_call": {
                5001: {
                    "date": "2026-05-11",
                    "chamber": "H",
                    "votes": [
                        {"people_id": 7001, "vote_text": "Yea"},
                        {"people_id": 7002, "vote_text": "Nay"},
                    ],
                },
                5002: {
                    "date": "2026-05-09",
                    "chamber": "S",
                    "votes": [
                        {"people_id": 7001, "vote_text": "Yea"},
                        {"people_id": 7003, "vote_text": "Yea"},
                    ],
                },
            }[id],
        },
    }

    with patch.object(legiscan, "_call", new=_canned_call(payloads)):
        index = asyncio.run(legiscan.build_state_vote_index("CT", bill_limit=10))

    # Three distinct members.
    assert set(index.keys()) == {"7001", "7002", "7003"}

    # 7001 voted on both calls; newer (clean-energy, 2026-05-11) first.
    rep1 = index["7001"]
    assert [r["title"] for r in rep1] == ["Clean Energy Act", "Prescription Drug Pricing Act"]
    assert rep1[0]["member_vote"] == "Yea"
    assert rep1[0]["category"] == "environment"
    assert rep1[1]["category"] == "healthcare"

    # 7002 only voted on the energy bill.
    assert len(index["7002"]) == 1
    assert index["7002"][0]["member_vote"] == "Nay"

    # Cache write happened.
    cached = stub_ai_cache["legiscan:vote_index:CT"]
    assert cached == index


def test_build_index_caches_empty_when_no_rollcalls(stub_ai_cache, with_legiscan_key):
    """Quiet session -> persist the empty index so we don't re-burn rate
    limit on every refresh. Otherwise a state with no recent roll calls would
    refetch the entire masterlist + every bill on every poll."""
    import asyncio
    from api import legiscan

    payloads = {
        "getSessionList": {"sessions": [{"session_id": 9002}]},
        "getMasterList": {
            "masterlist": {
                "session": {"session_id": 9002},
                "1": {"bill_id": 201, "number": "HB-99", "title": "Some Bill",
                       "last_action_date": "2026-01-01"},
            },
        },
        "getBill": lambda id, **_kw: {"bill": {"title": "Some Bill", "votes": []}},
    }

    with patch.object(legiscan, "_call", new=_canned_call(payloads)):
        index = asyncio.run(legiscan.build_state_vote_index("NJ", bill_limit=5))

    assert index == {}
    assert stub_ai_cache.get("legiscan:vote_index:NJ") == {}


# ---------- get_legislator_votes index fast-path ----------


def test_get_votes_reads_from_prebuilt_index(stub_ai_cache, with_legiscan_key):
    """The fast path: when the index is in cache, no upstream calls happen and
    the rep gets exactly their slice."""
    import asyncio
    from api import legiscan

    # Pre-load an index and a profile lookup so we don't hit upstream at all.
    stub_ai_cache["legiscan:vote_index:CT"] = {
        "7042": [
            {"title": "Affordable Housing Act", "date": "2026-04-20",
             "member_vote": "Yea", "category": "housing", "chamber": "H"},
        ],
    }
    stub_ai_cache["legiscan:profile:7042"] = {
        "people_id": 7042, "name": "Test Rep", "state": "CT", "chamber": "House",
        "sponsored_bills": [],
    }

    called = {"n": 0}

    async def boom_call(op, **kw):
        called["n"] += 1
        raise AssertionError(f"index fast-path should not call upstream (op={op})")

    with patch.object(legiscan, "_call", new=boom_call):
        rows = asyncio.run(legiscan.get_legislator_votes(7042))

    assert called["n"] == 0
    assert len(rows) == 1
    assert rows[0]["category"] == "housing"
    # Result was cached for the rep so a re-read short-circuits even faster.
    assert stub_ai_cache["legiscan:votes:7042"] == rows


def test_get_votes_index_hit_with_empty_slice_still_short_circuits(
    stub_ai_cache, with_legiscan_key,
):
    """A rep who appears in no roll calls in the window gets an honest [].
    Critically, we DON'T fall through to the sponsored-only probe — the index
    is authoritative when present, otherwise non-voters would still incur a
    per-request fan-out."""
    import asyncio
    from api import legiscan

    stub_ai_cache["legiscan:vote_index:CT"] = {
        "8888": [{"title": "X", "date": "2026-01-01", "member_vote": "Yea",
                  "category": "economy", "chamber": "S"}],
    }
    stub_ai_cache["legiscan:profile:7042"] = {
        "people_id": 7042, "name": "Q. Backbencher", "state": "CT", "chamber": "House",
        # Note: has sponsored bills, so fallback path WOULD do work — proving
        # the index short-circuit is what's keeping us out.
        "sponsored_bills": [{"bill_id": 999, "number": "HB-9"}],
    }

    called = {"n": 0}

    async def boom_call(op, **kw):
        called["n"] += 1
        raise AssertionError("should not fall back when index is present")

    with patch.object(legiscan, "_call", new=boom_call):
        rows = asyncio.run(legiscan.get_legislator_votes(7042))

    assert rows == []
    assert called["n"] == 0


def test_get_votes_falls_back_to_sponsored_when_no_index(
    stub_ai_cache, with_legiscan_key,
):
    """Cold cache (no vote index yet) -> sponsored-only probe runs, same as
    pre-Track-1 behavior. Returns [] for non-sponsors, real rows for sponsors
    on recently-voted bills."""
    import asyncio
    from api import legiscan

    # Profile pre-loaded; no vote_index for this state.
    stub_ai_cache["legiscan:profile:7042"] = {
        "people_id": 7042, "name": "Sponsor Rep", "state": "CT", "chamber": "House",
        "sponsored_bills": [{"bill_id": 555, "number": "HB-5"}],
    }

    payloads = {
        "getBill": lambda id, **_kw: {
            "bill": {
                "title": "Renewable Energy Procurement Act",
                "votes": [{"roll_call_id": 9000, "date": "2026-03-15", "chamber": "H"}],
            },
        },
        "getRollCall": lambda id, **_kw: {
            "roll_call": {
                "date": "2026-03-15", "chamber": "H",
                "votes": [{"people_id": 7042, "vote_text": "Yea"}],
            },
        },
    }

    with patch.object(legiscan, "_call", new=_canned_call(payloads)):
        rows = asyncio.run(legiscan.get_legislator_votes(7042))

    assert len(rows) == 1
    assert rows[0]["member_vote"] == "Yea"
    assert rows[0]["category"] == "environment"
