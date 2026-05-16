"""Tests for /api/reps/{bioguide_id}/funding-lite.

Locks in the probe-all-fec_ids fix: reps with prior House service have a stale
House FEC ID first in fec_ids[], so naive fec_ids[0] returns {} under the
current-cycle filter and pins has_data:false. The endpoint must probe every
fec_id in parallel and pick the first one with real receipts.

Imports of `api.*` are deferred into the test bodies so they happen AFTER
conftest's session fixture sets FUU_DB_PATH — otherwise `db` captures a stale
DB_PATH at collection time and bleeds into downstream pipeline tests.
"""
import uuid


def _fake_bioguide() -> str:
    return f"T{uuid.uuid4().hex[:6].upper()}"


def _stub_async(value):
    async def _coro(*_a, **_kw):
        return value
    return _coro


def test_funding_lite_probes_all_fec_ids_when_first_is_stale(client, monkeypatch):
    """Stale first fec_id (e.g. old House ID), live second. Should pick the live one."""
    from api import legislators, openfec, whoboughtmyrep

    bioguide = _fake_bioguide()

    monkeypatch.setattr(whoboughtmyrep, "get_rep_by_bioguide", _stub_async(None))
    monkeypatch.setattr(legislators, "get_by_bioguide", _stub_async({
        "bioguide_id": bioguide,
        "fec_ids": ["H6STALE0001", "S2LIVE0001"],
    }))

    live_totals = {
        "total_receipts": 27_800_000,
        "total_pac_contributions": 62_000,
        "total_small_individual": 4_100_000,
    }

    async def fake_totals(fec_id, *_a, **_kw):
        return live_totals if fec_id == "S2LIVE0001" else {}
    monkeypatch.setattr(openfec, "get_candidate_totals", fake_totals)

    r = client.get(f"/api/reps/{bioguide}/funding-lite")
    assert r.status_code == 200
    body = r.json()
    assert body["has_data"] is True
    assert body["source"] == "fec"
    assert body["total_raised"] == 27_800_000
    assert body["pac_total"] == 62_000
    assert body["small_donor_total"] == 4_100_000


def test_funding_lite_returns_no_data_when_all_fec_ids_empty(client, monkeypatch):
    """Every fec_id returns {}. Should land in the has_data:false branch, not a $0 success."""
    from api import legislators, openfec, whoboughtmyrep

    bioguide = _fake_bioguide()

    monkeypatch.setattr(whoboughtmyrep, "get_rep_by_bioguide", _stub_async(None))
    monkeypatch.setattr(legislators, "get_by_bioguide", _stub_async({
        "bioguide_id": bioguide,
        "fec_ids": ["H6DEAD0001", "S2DEAD0001"],
    }))
    monkeypatch.setattr(openfec, "get_candidate_totals", _stub_async({}))

    r = client.get(f"/api/reps/{bioguide}/funding-lite")
    assert r.status_code == 200
    body = r.json()
    assert body["has_data"] is False
    assert body["source"] == "none"
    assert "total_raised" not in body


def test_funding_lite_uses_wbmr_when_available(client, monkeypatch):
    """WBMR present short-circuits before the FEC probe."""
    from api import openfec, whoboughtmyrep

    bioguide = _fake_bioguide()

    monkeypatch.setattr(whoboughtmyrep, "get_rep_by_bioguide", _stub_async({
        "bioguide_id": bioguide,
        "any": "payload",
    }))
    monkeypatch.setattr(whoboughtmyrep, "normalize_rep_funding", lambda _w: {
        "total_raised": 1_000_000,
        "pac_total": 200_000,
        "small_donor_total": 50_000,
    })

    def _boom(*_a, **_kw):
        raise AssertionError("openfec should not be called when WBMR has data")
    monkeypatch.setattr(openfec, "get_candidate_totals", _boom)

    r = client.get(f"/api/reps/{bioguide}/funding-lite")
    assert r.status_code == 200
    body = r.json()
    assert body["has_data"] is True
    assert body["source"] == "wbmr"
    assert body["total_raised"] == 1_000_000
