"""
Fudge Ur Uncle - Backend Server
=================================
FastAPI server that aggregates data from multiple APIs
into the unified endpoints the frontend needs.

Run:  python server.py
Docs: http://localhost:8000/docs
"""

import asyncio
import json
import os
import traceback
from contextlib import asynccontextmanager
from hashlib import sha1
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from api import legislators, openfec, congress_gov, whoboughtmyrep, events
from api import guardian, news, ai_summary, stance_analysis, promises, legiscan, state_sites
from api import ai_cache, assistant_chat
from api.alerts_router import router as alerts_router
from api.auth import router as auth_router, get_current_user
from api.upcoming_votes_router import router as upcoming_votes_router
import config


# ============================================================
# BACKGROUND REFRESH
# Railway volumes can't be shared across services, so the cron-style
# refresh has to live inside the web process to write to the same DB
# the web reads. Gated on FUU_BACKGROUND_REFRESH=1 so dev `python
# server.py` doesn't hammer external APIs.
# ============================================================

_REFRESH_INTERVAL_SECONDS = int(os.environ.get("FUU_REFRESH_INTERVAL_SECONDS", "21600"))   # 6h
_DONATIONS_INTERVAL_SECONDS = int(os.environ.get("FUU_DONATIONS_INTERVAL_SECONDS", "86400"))  # 24h
_REFRESH_INITIAL_DELAY = int(os.environ.get("FUU_REFRESH_INITIAL_DELAY", "30"))            # 30s
_DONATIONS_INITIAL_DELAY = int(os.environ.get("FUU_DONATIONS_INITIAL_DELAY", "60"))        # 60s
_DONATION_STATES = tuple(s.strip().upper() for s in os.environ.get(
    "FUU_DONATION_STATES", "CT,NY,NJ,CA,MA"
).split(",") if s.strip())


def _sync_refresh() -> None:
    # Runs in a thread executor because refresh.run() calls asyncio.run()
    # internally; can't be invoked from inside the server's event loop.
    from alerts.refresh import run as refresh_run
    refresh_run()


def _sync_donations_ingest() -> None:
    import asyncio as _a
    from alerts.ingest_fec import ingest as fec_ingest
    from alerts.ingest_ftm import ingest_state as ftm_ingest

    print("[bg-donations] FEC ingest (days=365)")
    _a.run(fec_ingest(days=365))
    for state in _DONATION_STATES:
        print(f"[bg-donations] FTM ingest {state}")
        try:
            _a.run(ftm_ingest(state=state))
        except Exception as e:
            print(f"[bg-donations] FTM {state} failed: {e}")
            traceback.print_exc()


async def _refresh_loop() -> None:
    await asyncio.sleep(_REFRESH_INITIAL_DELAY)
    loop = asyncio.get_event_loop()
    while True:
        try:
            print("[bg-refresh] starting refresh tick")
            await loop.run_in_executor(None, _sync_refresh)
            print("[bg-refresh] refresh tick complete")
        except Exception as e:
            print(f"[bg-refresh] tick failed: {e}")
            traceback.print_exc()
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)


async def _donations_loop() -> None:
    await asyncio.sleep(_DONATIONS_INITIAL_DELAY)
    loop = asyncio.get_event_loop()
    while True:
        try:
            print("[bg-donations] starting donations tick")
            await loop.run_in_executor(None, _sync_donations_ingest)
            print("[bg-donations] donations tick complete")
            # Kick off a refresh immediately so the new donations get
            # scored against existing votes without waiting for the next
            # scheduled refresh tick (which could be ~6h away).
            print("[bg-donations] triggering post-ingest refresh")
            await loop.run_in_executor(None, _sync_refresh)
            print("[bg-donations] post-ingest refresh complete")
        except Exception as e:
            print(f"[bg-donations] tick failed: {e}")
            traceback.print_exc()
        await asyncio.sleep(_DONATIONS_INTERVAL_SECONDS)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        import db
        db.init_db()
    except Exception as e:
        print(f"[startup] init_db skipped: {e}")

    if os.environ.get("FUU_BACKGROUND_REFRESH", "0") != "1":
        print("[startup] background refresh DISABLED (set FUU_BACKGROUND_REFRESH=1 to enable)")
    else:
        asyncio.create_task(_refresh_loop())
        asyncio.create_task(_donations_loop())
        print(
            f"[startup] background tasks scheduled: "
            f"refresh every {_REFRESH_INTERVAL_SECONDS}s, "
            f"donations every {_DONATIONS_INTERVAL_SECONDS}s"
        )

    yield


app = FastAPI(
    title="Fudge Ur Uncle API",
    description="Politician accountability tracker.",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(upcoming_votes_router)


# ============================================================
# HEALTH
# ============================================================

def _health_payload():
    return {
        "app": "Fudge Ur Uncle",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "api_keys_configured": {
            "data_gov": config.DATA_GOV_API_KEY != "DEMO_KEY",
            "whoboughtmyrep": bool(config.WHOBOUGHTMYREP_API_KEY),
            "legiscan": bool(config.LEGISCAN_API_KEY),
            "ftm": bool(config.FTM_API_KEY),
            "openai": bool(config.OPENAI_API_KEY),
            "newsapi": bool(config.NEWSAPI_KEY),
            "guardian": bool(config.GUARDIAN_API_KEY),
        },
    }


@app.get("/", tags=["health"])
async def root():
    return _health_payload()


@app.get("/api/health", tags=["health"])
async def health():
    return _health_payload()


# ============================================================
# REPRESENTATIVES  -  /api/reps
# ============================================================

@app.get("/api/reps/by-state/{state}", tags=["representatives"])
async def get_reps_by_state(state: str):
    """
    Get all federal representatives for a state.
    
    This endpoint is FAST - it returns just legislator basics without
    funding. The frontend loads funding per-rep via /api/reps/{id}/funding-lite.
    """
    legs = await legislators.search_by_state(state.upper())
    if not legs:
        return {"state": state.upper(), "count": 0, "representatives": []}

    # Return reps with funding set to None - frontend fetches per-rep
    reps = [{**leg, "funding": None} for leg in legs]
    return {"state": state.upper(), "count": len(reps), "representatives": reps}


@app.get("/api/reps/{bioguide_id}/funding-lite", tags=["representatives"])
async def get_rep_funding_lite(bioguide_id: str):
    """
    Lightweight funding summary for a single rep.
    Used by dashboard cards to lazy-load funding after the rep list renders.

    Cached in ai_cache for 24h. Campaign filings update quarterly, so 24h is
    well inside the data's natural freshness window. The empty-data result is
    cached too so reps WBMR + FEC don't cover don't re-hit upstream on every
    dashboard mount — a 5-rep fan-out used to issue 5–10 upstream calls each
    time the user opened the app.
    """
    cache_key = f"funding_lite:{bioguide_id}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    wbmr = await whoboughtmyrep.get_rep_by_bioguide(bioguide_id)
    if not wbmr:
        # WBMR has no data - try FEC as fallback
        leg = await legislators.get_by_bioguide(bioguide_id)
        if leg and leg.get("fec_ids"):
            # Reps with prior House service have their old House FEC ID listed
            # first; get_candidate_totals filters by current cycle and returns
            # {} for it. Probe every fec_id in parallel and pick the first one
            # with real receipts. Same pattern as get_full_profile below.
            fec_ids = leg["fec_ids"]
            all_totals = await asyncio.gather(*[openfec.get_candidate_totals(fid) for fid in fec_ids])
            fec_totals = next((t for t in all_totals if t.get("total_receipts")), all_totals[0])
            if fec_totals.get("total_receipts"):
                result = {
                    "bioguide_id": bioguide_id,
                    "total_raised": fec_totals.get("total_receipts", 0),
                    "pac_total": fec_totals.get("total_pac_contributions", 0),
                    "small_donor_total": fec_totals.get("total_small_individual", 0),
                    "source": "fec",
                    "has_data": True,
                }
                ai_cache.set(cache_key, result, ttl_hours=24)
                return result
        result = {"bioguide_id": bioguide_id, "has_data": False, "source": "none"}
        # Negative cache gets a short TTL (15min) — long enough to absorb a
        # dashboard fan-out (5–7 reps loading at once) but short enough that
        # transient WBMR/FEC misses self-heal on the next page open. Murphy
        # got pinned with has_data:false for 24h because WBMR was flaky AND
        # the FEC fallback hit a dead House ID; users saw "—" on his card
        # all day. 0.25h keeps the upstream-shield benefit without the rot.
        ai_cache.set(cache_key, result, ttl_hours=0.25)
        return result

    funding = whoboughtmyrep.normalize_rep_funding(wbmr)
    result = {
        "bioguide_id": bioguide_id,
        "total_raised": funding["total_raised"],
        "pac_total": funding["pac_total"],
        "small_donor_total": funding["small_donor_total"],
        "source": "wbmr",
        "has_data": True,
    }
    ai_cache.set(cache_key, result, ttl_hours=24)
    return result

@app.get("/api/reps/search", tags=["representatives"])
async def search_reps(q: str = Query(..., min_length=2)):
    """Search representatives by name."""
    results = await legislators.search_by_name(q)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/search/unified", tags=["search"])
async def search_unified(q: str = Query(..., min_length=2), state: Optional[str] = None):
    """
    Combined federal + state legislator name search. Federal results come from
    the congress-legislators GitHub data; state results require a `state` param
    (e.g. CT) and come from the cached Legiscan roster. Each result is tagged
    with `level: "federal" | "state"` so the frontend can route clicks.
    """
    federal_task = legislators.search_by_name(q)
    state_task = (
        legiscan.search_state_legislators(state, q)
        if state else asyncio.sleep(0, result=[])
    )
    federal, state_hits = await asyncio.gather(federal_task, state_task)

    results = [{**r, "level": "federal"} for r in federal] + \
              [{**r, "level": "state"} for r in state_hits]

    return {
        "query": q,
        "state": (state or "").upper() or None,
        "count": len(results),
        "results": results,
    }


@app.get("/api/reps/{bioguide_id}", tags=["representatives"])
async def get_rep_detail(bioguide_id: str):
    """Get full profile for a representative."""
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    fec_ids = leg.get("fec_ids", [])
    funding = {}
    top_contributors = []
    if fec_ids:
        all_totals = await asyncio.gather(*[openfec.get_candidate_totals(fid) for fid in fec_ids])
        active_id = fec_ids[0]
        for fid, totals in zip(fec_ids, all_totals):
            if totals.get("total_receipts"):
                funding = totals
                active_id = fid
                break
        else:
            funding = all_totals[0]
        top_contributors = await openfec.get_top_contributors(active_id)

    votes = await congress_gov.get_member_votes(bioguide_id, govtrack_id=leg.get("govtrack_id"))
    sponsored = await congress_gov.get_sponsored_bills(bioguide_id, limit=5)

    return {
        "profile": leg,
        "funding": {
            "summary": funding,
            "top_contributors": top_contributors,
        },
        "voting_record": votes,
        "sponsored_bills": sponsored,
    }


# ============================================================
# STATE REPRESENTATIVES  -  /api/state-reps (Legiscan)
# ============================================================

@app.get("/api/state-reps/by-state/{state}", tags=["state-reps"])
async def get_state_reps_by_state(state: str):
    """Get all current-session state legislators for a state via Legiscan."""
    results = await legiscan.get_state_legislators(state.upper())
    return {
        "state": state.upper(),
        "count": len(results),
        "source": "legiscan" if config.LEGISCAN_API_KEY else "sample",
        "representatives": results,
    }


@app.get("/api/state-reps/{people_id}", tags=["state-reps"])
async def get_state_rep_detail(people_id: int):
    """Get profile + sponsored bills for a state legislator via Legiscan."""
    profile = await legiscan.get_legislator(people_id)
    if not profile:
        raise HTTPException(404, f"State legislator not found: {people_id}")
    return profile


@app.get("/api/state-reps/{people_id}/votes", tags=["state-reps"])
async def get_state_rep_votes(people_id: int, limit: int = 20):
    """Recent roll-call votes for a state legislator (Legiscan getBill + getRollCall)."""
    profile = await legiscan.get_legislator(people_id)
    if not profile:
        raise HTTPException(404, f"State legislator not found: {people_id}")
    votes = await legiscan.get_legislator_votes(people_id)
    return {
        "people_id": people_id,
        "total_votes": len(votes),
        "votes": votes[:limit],
    }


@app.get("/api/state-reps/{people_id}/stances", tags=["state-reps"])
async def get_state_rep_stances(people_id: int):
    """AI-analyzed voting positions for a state legislator. Requires OPENAI_API_KEY."""
    profile = await legiscan.get_legislator(people_id)
    if not profile:
        raise HTTPException(404, f"State legislator not found: {people_id}")

    votes = await legiscan.get_legislator_votes(people_id)
    sponsored = profile.get("sponsored_bills") or []

    stances = await stance_analysis.get_stance_analysis(
        cache_key=f"stances:state:{people_id}",
        name=profile.get("name", ""),
        party=profile.get("party", ""),
        chamber=profile.get("chamber", ""),
        votes=votes,
        sponsored_bills=sponsored,
    )

    return {
        "stances": stances,
        "ai_available": bool(config.OPENAI_API_KEY),
        "legislator": profile.get("name", ""),
    }


@app.get("/api/state-reps/{people_id}/promises", tags=["state-reps"])
async def get_state_rep_promises(people_id: int):
    """Scrape a state legislator's bio site for stated positions and score vs. votes."""
    profile = await legiscan.get_legislator(people_id)
    if not profile:
        raise HTTPException(404, f"State legislator not found: {people_id}")

    website = state_sites.derive_website(profile)
    if not website:
        return {
            "promises": None,
            "source_url": "",
            "ai_available": bool(config.OPENAI_API_KEY),
            "scraped": False,
            "legislator": profile.get("name", ""),
        }

    votes = await legiscan.get_legislator_votes(people_id)
    sponsored = profile.get("sponsored_bills") or []

    result = await promises.get_promises(
        cache_key=f"promises:state:{people_id}",
        name=profile.get("name", ""),
        party=profile.get("party", ""),
        chamber=profile.get("chamber", ""),
        website=website,
        votes=votes,
        sponsored_bills=sponsored,
    )

    return {
        "promises": (result or {}).get("promises"),
        "source_url": (result or {}).get("source_url") or website,
        "ai_available": bool(config.OPENAI_API_KEY),
        "scraped": result is not None,
        "legislator": profile.get("name", ""),
    }


# ============================================================
# FUNDING  -  /api/funding
# ============================================================

@app.get("/api/funding/{bioguide_id}", tags=["funding"])
async def get_funding_detail(bioguide_id: str):
    """Full funding breakdown for a representative."""
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    fec_ids = leg.get("fec_ids", [])
    fec_totals = {}
    top_employers = []
    if fec_ids:
        all_totals = await asyncio.gather(*[openfec.get_candidate_totals(fid) for fid in fec_ids])
        active_id = fec_ids[0]
        for fid, totals in zip(fec_ids, all_totals):
            if totals.get("total_receipts"):
                fec_totals = totals
                active_id = fid
                break
        else:
            fec_totals = all_totals[0]
        top_employers = await openfec.get_top_employers(active_id)

    wbmr_data = await whoboughtmyrep.get_rep_by_bioguide(bioguide_id)

    return {
        "representative": {
            "name": leg["name"],
            "bioguide_id": bioguide_id,
            "state": leg["state"],
            "party": leg["party"],
        },
        "fec_totals": fec_totals,
        "industry_breakdown": (wbmr_data.get("top_industries", []) if wbmr_data else []),
        "top_donors": top_employers,
        "pac_vs_individual": {
            "pac_total": fec_totals.get("total_pac_contributions", 0),
            "individual_total": fec_totals.get("total_individual_contributions", 0),
            "small_dollar": fec_totals.get("total_small_individual", 0),
        },
    }


@app.get("/api/funding/{bioguide_id}/industries", tags=["funding"])
async def get_funding_by_industry(bioguide_id: str, limit: int = 15):
    """Industry-level funding with PAC hop tracing."""
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404)

    wbmr = await whoboughtmyrep.get_rep_by_bioguide(bioguide_id)
    industries = (wbmr.get("top_industries", []) if wbmr else [])[:limit]
    return {
        "representative": leg["name"],
        "industries": industries,
    }


# ============================================================
# VOTES  -  /api/votes
# ============================================================

@app.get("/api/votes/{bioguide_id}", tags=["votes"])
async def get_voting_record(
    bioguide_id: str,
    category: Optional[str] = None,
    limit: int = 20,
):
    """Get voting record for a representative."""
    leg = await legislators.get_by_bioguide(bioguide_id)
    votes = await congress_gov.get_member_votes(bioguide_id, govtrack_id=leg.get("govtrack_id") if leg else None)

    if category:
        votes = [v for v in votes if v.get("category", "").lower() == category.lower()]

    return {
        "bioguide_id": bioguide_id,
        "total_votes": len(votes),
        "votes": votes[:limit],
    }


# ============================================================
# BILLS  -  /api/bills
# ============================================================

@app.get("/api/bills/search", tags=["bills"])
async def search_bills(q: str = Query(..., min_length=2), limit: int = 20):
    """Search bills by keyword."""
    results = await congress_gov.search_bills(q, limit=limit)
    return {"query": q, "count": len(results), "bills": results}


@app.get("/api/bills/{congress}/{bill_type}/{bill_number}", tags=["bills"])
async def get_bill(congress: int, bill_type: str, bill_number: int):
    """Get details for a specific bill."""
    bill = await congress_gov.get_bill_detail(congress, bill_type, bill_number)
    if not bill:
        raise HTTPException(404, "Bill not found")
    return bill


# ============================================================
# EVENTS  -  /api/events
# ============================================================

@app.get("/api/events", tags=["events"])
async def get_events(
    state: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    """Upcoming federal committee hearings from Congress.gov."""
    event_list = await events.fetch_events(limit=limit)
    return {"state": state, "count": len(event_list), "events": event_list}


@app.get("/api/events/article", tags=["events"])
async def get_event_article(q: str = Query(default="")):
    """Find the most relevant news article for a committee hearing (NewsAPI primary, Guardian fallback)."""
    if not q or len(q.strip()) < 3:
        return {"article": None}
    article = await news.search_article(q)
    if article is None:
        article = await guardian.search_article(q)
    return {"article": article}


@app.get("/api/events/summary", tags=["events"])
async def get_event_summary(
    title: str = Query(default=""),
    chamber: str = Query(""),
    meeting_type: str = Query(""),
    committee: str = Query(""),
    bills: str = Query(""),
):
    """Generate an AI plain-English summary for a committee meeting."""
    if not title or len(title.strip()) < 3:
        return {"summary": None}
    summary = await ai_summary.get_event_summary(title, chamber, meeting_type, committee, bills)
    return {"summary": summary}


# ============================================================
# ASSISTANT  -  /api/assistant
# ============================================================

class ChatBody(BaseModel):
    messages: list[dict]
    context: Optional[dict] = None


@app.post("/api/assistant/chat", tags=["ai"])
async def assistant_chat_endpoint(
    body: ChatBody,
    current_user: dict = Depends(get_current_user),
):
    """Civics learning assistant. Auth required so we can scope cache + (future) rate limit per user."""
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must be non-empty")
    if len(body.messages) > 30:
        raise HTTPException(status_code=400, detail="messages must be <= 30 turns")

    payload = json.dumps(body.messages, sort_keys=True) + json.dumps(body.context or {}, sort_keys=True)
    cache_key = f"chat:{current_user['id']}:{sha1(payload.encode()).hexdigest()}"

    cached = ai_cache.get(cache_key)
    if cached is not None:
        return {"reply": cached.get("reply"), "cached": True}

    reply = await assistant_chat.get_chat_response(body.messages, body.context)
    if reply:
        ai_cache.set(cache_key, {"reply": reply}, ttl_hours=24)
    return {"reply": reply, "cached": False}


# ============================================================
# COMPOSITE  -  /api/profile
# ============================================================

@app.get("/api/profile/{bioguide_id}", tags=["composite"])
async def get_full_profile(bioguide_id: str):
    """
    Full politician profile combining all data sources.

    Cached in ai_cache for 6h. Composite endpoint fans out ~5 upstream calls
    (Congress.gov bills + votes, OpenFEC totals + employers, WBMR) so cold
    hits run 2-5s — every click on a rep card used to re-pay that cost.
    6h TTL balances "recent votes appear within a browsing session" against
    "browsing the same rep repeatedly is instant."
    """
    cache_key = f"profile:{bioguide_id}"
    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    leg_task = legislators.get_by_bioguide(bioguide_id)
    sponsored_task = congress_gov.get_sponsored_bills(bioguide_id, limit=5)
    wbmr_task = whoboughtmyrep.get_rep_by_bioguide(bioguide_id)

    leg, sponsored, wbmr = await asyncio.gather(leg_task, sponsored_task, wbmr_task)

    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    votes = await congress_gov.get_member_votes(bioguide_id, govtrack_id=leg.get("govtrack_id"))

    fec_totals = {}
    top_employers = []
    fec_ids = leg.get("fec_ids", [])
    if fec_ids:
        # Reps with prior House service have their old House FEC ID listed
        # first (e.g. Murphy: H6CT05124 from 2006-12); get_candidate_totals
        # filters by current_cycle and returns {} for it. Probe every fec_id
        # in parallel, pick the first one with real receipts, then fetch
        # employers for that winning ID.
        all_totals = await asyncio.gather(*[openfec.get_candidate_totals(fid) for fid in fec_ids])
        active_id = fec_ids[0]
        for fid, totals in zip(fec_ids, all_totals):
            if totals.get("total_receipts"):
                fec_totals = totals
                active_id = fid
                break
        else:
            fec_totals = all_totals[0]
        top_employers = await openfec.get_top_employers(active_id)

    funding = whoboughtmyrep.normalize_rep_funding(wbmr)
    funding["individual_total"] = fec_totals.get("total_individual_contributions", 0)
    funding["top_donors"] = top_employers

    if not wbmr and fec_totals:
        funding["total_raised"] = fec_totals.get("total_receipts", 0)
        funding["pac_total"] = fec_totals.get("total_pac_contributions", 0)
        funding["small_donor_total"] = fec_totals.get("total_small_individual", 0)

    yea_count = sum(1 for v in votes if v.get("member_vote") == "Yea")
    nay_count = sum(1 for v in votes if v.get("member_vote") == "Nay")

    result = {
        "profile": leg,
        "funding": funding,
        "votes": {
            "recent": votes[:10],
            "total_tracked": len(votes),
            "yea_count": yea_count,
            "nay_count": nay_count,
        },
        "sponsored_bills": sponsored,
        "promise_score": None,
        "contact": {
            "phone": leg.get("phone", ""),
            "website": leg.get("website", ""),
            "office": leg.get("office", ""),
            "contact_form": leg.get("contact_form", ""),
        },
    }
    # Don't pin a 6h cache row if WBMR served an obviously incomplete record.
    # Signature: WBMR returned *something* (so we exited the "not wbmr" branch
    # that fills from FEC), but top_industries is empty despite a non-trivial
    # total_raised. Real cause seen in the wild: Murphy got cached with
    # total_raised=$12.5M, top_industries=[], pac_total=$0 — but the next live
    # call returned $27.8M, 10 industries, $62K PAC. WBMR briefly served a
    # stripped record and the 6h TTL pinned it. Skip the write so the next
    # request retries upstream instead.
    wbmr_looks_thin = (
        wbmr is not None
        and not funding.get("top_industries")
        and (funding.get("total_raised") or 0) > 100_000
    )
    if not wbmr_looks_thin:
        ai_cache.set(cache_key, result, ttl_hours=6)
    return result


# ============================================================
# STANCES  -  /api/profile/{id}/stances
# ============================================================

@app.get("/api/profile/{bioguide_id}/promises", tags=["composite"])
async def get_promises(bioguide_id: str):
    """Scrape rep's official .gov site for stated positions, score against voting record. Requires OPENAI_API_KEY."""
    leg_task = legislators.get_by_bioguide(bioguide_id)
    sponsored_task = congress_gov.get_sponsored_bills(bioguide_id, limit=8)
    leg, sponsored = await asyncio.gather(leg_task, sponsored_task)

    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    votes = await congress_gov.get_member_votes(bioguide_id, govtrack_id=leg.get("govtrack_id"))

    result = await promises.get_promises(
        cache_key=f"promises:{bioguide_id}",
        name=leg.get("name", ""),
        party=leg.get("party", ""),
        chamber=leg.get("chamber", ""),
        website=leg.get("website", ""),
        votes=votes,
        sponsored_bills=sponsored,
    )

    return {
        "promises": (result or {}).get("promises"),
        "source_url": (result or {}).get("source_url") or leg.get("website", ""),
        "ai_available": bool(config.OPENAI_API_KEY),
        "scraped": result is not None,
        "legislator": leg.get("name", ""),
    }


@app.get("/api/profile/{bioguide_id}/stances", tags=["composite"])
async def get_stances(bioguide_id: str):
    """AI-analyzed voting positions for a legislator. Requires OPENAI_API_KEY."""
    leg_task = legislators.get_by_bioguide(bioguide_id)
    sponsored_task = congress_gov.get_sponsored_bills(bioguide_id, limit=8)
    leg, sponsored = await asyncio.gather(leg_task, sponsored_task)

    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    votes = await congress_gov.get_member_votes(bioguide_id, govtrack_id=leg.get("govtrack_id"))

    stances = await stance_analysis.get_stance_analysis(
        cache_key=f"stances:{bioguide_id}",
        name=leg.get("name", ""),
        party=leg.get("party", ""),
        chamber=leg.get("chamber", ""),
        votes=votes,
        sponsored_bills=sponsored,
    )

    return {
        "stances": stances,
        "ai_available": bool(config.OPENAI_API_KEY),
        "legislator": leg.get("name", ""),
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("\n  Fudge Ur Uncle API Server")
    print("  ========================")
    print(f"  Swagger docs: http://localhost:{config.PORT}/docs")
    print(f"  API root:     http://localhost:{config.PORT}/")
    print()
    uvicorn.run(app, host=config.HOST, port=config.PORT)