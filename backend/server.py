"""
Fudge Ur Uncle - Backend Server
=================================
FastAPI server that aggregates data from multiple APIs
into the unified endpoints the frontend needs.

Run:  python server.py
Docs: http://localhost:8000/docs
"""

import asyncio
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from api import legislators, openfec, congress_gov, whoboughtmyrep, events
from api import guardian, news, ai_summary, stance_analysis, promises
from api.alerts_router import router as alerts_router
import config

app = FastAPI(
    title="Fudge Ur Uncle API",
    description="Politician accountability tracker.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)

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
    """
    wbmr = await whoboughtmyrep.get_rep_by_bioguide(bioguide_id)
    if not wbmr:
        # WBMR has no data - try FEC as fallback
        leg = await legislators.get_by_bioguide(bioguide_id)
        if leg and leg.get("fec_ids"):
            fec_totals = await openfec.get_candidate_totals(leg["fec_ids"][0])
            if fec_totals:
                return {
                    "bioguide_id": bioguide_id,
                    "total_raised": fec_totals.get("total_receipts", 0),
                    "pac_total": fec_totals.get("total_pac_contributions", 0),
                    "small_donor_total": fec_totals.get("total_small_individual", 0),
                    "source": "fec",
                    "has_data": True,
                }
        return {"bioguide_id": bioguide_id, "has_data": False, "source": "none"}

    funding = whoboughtmyrep.normalize_rep_funding(wbmr)
    return {
        "bioguide_id": bioguide_id,
        "total_raised": funding["total_raised"],
        "pac_total": funding["pac_total"],
        "small_donor_total": funding["small_donor_total"],
        "source": "wbmr",
        "has_data": True,
    }

@app.get("/api/reps/search", tags=["representatives"])
async def search_reps(q: str = Query(..., min_length=2)):
    """Search representatives by name."""
    results = await legislators.search_by_name(q)
    return {"query": q, "count": len(results), "results": results}


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
        funding = await openfec.get_candidate_totals(fec_ids[0])
        top_contributors = await openfec.get_top_contributors(fec_ids[0])

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
        fec_totals, top_employers = await asyncio.gather(
            openfec.get_candidate_totals(fec_ids[0]),
            openfec.get_top_employers(fec_ids[0]),
        )

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
# COMPOSITE  -  /api/profile
# ============================================================

@app.get("/api/profile/{bioguide_id}", tags=["composite"])
async def get_full_profile(bioguide_id: str):
    """Full politician profile combining all data sources."""
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
        fec_totals, top_employers = await asyncio.gather(
            openfec.get_candidate_totals(fec_ids[0]),
            openfec.get_top_employers(fec_ids[0]),
        )

    funding = whoboughtmyrep.normalize_rep_funding(wbmr)
    funding["individual_total"] = fec_totals.get("total_individual_contributions", 0)
    funding["top_donors"] = top_employers

    if not wbmr and fec_totals:
        funding["total_raised"] = fec_totals.get("total_receipts", 0)
        funding["pac_total"] = fec_totals.get("total_pac_contributions", 0)
        funding["small_donor_total"] = fec_totals.get("total_small_individual", 0)

    yea_count = sum(1 for v in votes if v.get("member_vote") == "Yea")
    nay_count = sum(1 for v in votes if v.get("member_vote") == "Nay")

    return {
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
        bioguide_id=bioguide_id,
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
        bioguide_id=bioguide_id,
        name=leg.get("name", ""),
        party=leg.get("party", ""),
        chamber=leg.get("chamber", ""),
        votes=votes,
        sponsored_bills=sponsored,
    )

    return {
        "stances": stances,
        "ai_available": stances is not None,
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