"""
Fudge Ur Uncle - Backend Server
=================================
FastAPI server that aggregates data from multiple APIs
into the unified endpoints the frontend needs.

Run:  python server.py
Docs: http://localhost:8000/docs  (auto-generated Swagger UI)
"""

import asyncio
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from api import legislators, openfec, congress_gov, whoboughtmyrep
import config

app = FastAPI(
    title="Fudge Ur Uncle API",
    description="Politician accountability tracker. Aggregates campaign finance, "
                "voting records, and representative data from public sources.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health", tags=["health"])
async def health():
    return await root()

@app.get("/", tags=["health"])
async def root():
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


# ============================================================
# REPRESENTATIVES  -  /api/reps
# ============================================================

@app.get("/api/reps/by-state/{state}", tags=["representatives"])
async def get_reps_by_state(state: str):
    """
    Get all federal representatives for a state.
    Combines legislator data with funding summaries.
    
    Example: /api/reps/by-state/CT
    """
    # Get basic legislator info
    legs = await legislators.search_by_state(state.upper())
    if not legs:
        raise HTTPException(404, f"No legislators found for state: {state}")

    # Enrich with funding data from WhoBoughtMyRep
    wbmr_reps = await whoboughtmyrep.get_reps(state=state.upper())
    funding_map = {r.get("name", "").lower(): r for r in wbmr_reps}

    enriched = []
    for leg in legs:
        name_key = leg["name"].lower()
        # Try partial match
        funding = None
        for fname, fdata in funding_map.items():
            if leg["last_name"].lower() in fname:
                funding = fdata
                break

        enriched.append({
            **leg,
            "funding": {
                "total_raised": funding.get("total_raised", 0) if funding else 0,
                "total_funding": funding.get("total_funding", 0) if funding else 0,
                "pac_total": funding.get("pac_total", 0) if funding else 0,
                "small_donor_total": funding.get("small_donor_total", 0) if funding else 0,
            } if funding else None,
        })

    return {"state": state.upper(), "count": len(enriched), "representatives": enriched}


@app.get("/api/reps/search", tags=["representatives"])
async def search_reps(q: str = Query(..., min_length=2)):
    """
    Search representatives by name.
    
    Example: /api/reps/search?q=Murphy
    """
    results = await legislators.search_by_name(q)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/reps/{bioguide_id}", tags=["representatives"])
async def get_rep_detail(bioguide_id: str):
    """
    Get full profile for a representative: bio + funding + votes.
    This is the main endpoint that powers the Politician Profile screen.
    
    Example: /api/reps/M001169
    """
    # Basic info
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    # Funding from OpenFEC
    fec_ids = leg.get("fec_ids", [])
    funding = {}
    top_contributors = []
    if fec_ids:
        funding = await openfec.get_candidate_totals(fec_ids[0])
        top_contributors = await openfec.get_top_contributors(fec_ids[0])

    # Voting record
    votes = await congress_gov.get_member_votes(bioguide_id)

    # Sponsored legislation
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
    """
    Full funding breakdown for a representative.
    Pulls from both OpenFEC (raw) and WhoBoughtMyRep (industry-attributed).
    
    Example: /api/funding/M001169
    """
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    fec_ids = leg.get("fec_ids", [])

    # Raw FEC totals
    fec_totals = {}
    if fec_ids:
        fec_totals = await openfec.get_candidate_totals(fec_ids[0])

    # Industry attribution from WhoBoughtMyRep
    wbmr_reps = await whoboughtmyrep.get_reps(state=leg.get("state"))
    wbmr_data = None
    for r in wbmr_reps:
        if leg["last_name"].lower() in r.get("name", "").lower():
            wbmr_data = r
            break

    return {
        "representative": {
            "name": leg["name"],
            "bioguide_id": bioguide_id,
            "state": leg["state"],
            "party": leg["party"],
        },
        "fec_totals": fec_totals,
        "industry_breakdown": wbmr_data.get("top_industries", []) if wbmr_data else [],
        "top_donors": wbmr_data.get("top_donors", []) if wbmr_data else [],
        "pac_vs_individual": {
            "pac_total": fec_totals.get("total_pac_contributions", 0),
            "individual_total": fec_totals.get("total_individual_contributions", 0),
            "small_dollar": fec_totals.get("total_small_individual", 0),
        },
    }


@app.get("/api/funding/{bioguide_id}/industries", tags=["funding"])
async def get_funding_by_industry(bioguide_id: str, limit: int = 15):
    """
    Industry-level funding with PAC hop tracing.
    Uses WhoBoughtMyRep's attribution engine.
    """
    wbmr_reps = await whoboughtmyrep.get_reps()
    leg = await legislators.get_by_bioguide(bioguide_id)
    if not leg:
        raise HTTPException(404)

    for r in wbmr_reps:
        if leg["last_name"].lower() in r.get("name", "").lower():
            return {
                "representative": leg["name"],
                "industries": r.get("top_industries", [])[:limit],
            }

    return {"representative": leg["name"], "industries": []}


# ============================================================
# VOTES  -  /api/votes
# ============================================================

@app.get("/api/votes/{bioguide_id}", tags=["votes"])
async def get_voting_record(
    bioguide_id: str,
    category: Optional[str] = None,
    limit: int = 20,
):
    """
    Get voting record for a representative.
    Optionally filter by issue category.
    
    Example: /api/votes/M001169?category=healthcare
    """
    votes = await congress_gov.get_member_votes(bioguide_id)

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
    """
    Search bills by keyword.
    
    Example: /api/bills/search?q=climate
    """
    results = await congress_gov.search_bills(q, limit=limit)
    return {"query": q, "count": len(results), "bills": results}


@app.get("/api/bills/{congress}/{bill_type}/{bill_number}", tags=["bills"])
async def get_bill(congress: int, bill_type: str, bill_number: int):
    """
    Get details for a specific bill.
    
    Example: /api/bills/119/s/1821
    """
    bill = await congress_gov.get_bill_detail(congress, bill_type, bill_number)
    if not bill:
        raise HTTPException(404, "Bill not found")
    return bill


# ============================================================
# COMPOSITE  -  /api/profile  (powers the full politician screen)
# ============================================================

@app.get("/api/profile/{bioguide_id}", tags=["composite"])
async def get_full_profile(bioguide_id: str):
    """
    THE BIG ONE: Full politician profile combining all data sources.
    This single endpoint powers the entire Politician Profile screen
    in the app, including funding, votes, and basic info.
    
    Example: /api/profile/M001169
    """
    # Run all fetches in parallel
    leg_task = legislators.get_by_bioguide(bioguide_id)
    votes_task = congress_gov.get_member_votes(bioguide_id)
    sponsored_task = congress_gov.get_sponsored_bills(bioguide_id, limit=5)
    wbmr_task = whoboughtmyrep.get_reps()

    leg, votes, sponsored, wbmr_all = await asyncio.gather(
        leg_task, votes_task, sponsored_task, wbmr_task
    )

    if not leg:
        raise HTTPException(404, f"Legislator not found: {bioguide_id}")

    # Match WhoBoughtMyRep data
    wbmr = None
    for r in wbmr_all:
        if leg["last_name"].lower() in r.get("name", "").lower():
            wbmr = r
            break

    # Fetch FEC totals if we have an FEC ID
    fec_totals = {}
    fec_ids = leg.get("fec_ids", [])
    if fec_ids:
        fec_totals = await openfec.get_candidate_totals(fec_ids[0])

    # Compute promise score placeholder
    # In production, this comes from your own promise-tracking database
    promise_score = None  # TODO: Build promise tracking system

    # Compute vote stats
    yea_count = sum(1 for v in votes if v.get("member_vote") == "Yea")
    nay_count = sum(1 for v in votes if v.get("member_vote") == "Nay")

    return {
        "profile": leg,
        "funding": {
            "total_raised": wbmr.get("total_raised", 0) if wbmr else fec_totals.get("total_receipts", 0),
            "total_funding": wbmr.get("total_funding", 0) if wbmr else 0,
            "pac_total": wbmr.get("pac_total", 0) if wbmr else fec_totals.get("total_pac_contributions", 0),
            "individual_total": fec_totals.get("total_individual_contributions", 0),
            "small_donor_total": wbmr.get("small_donor_total", 0) if wbmr else fec_totals.get("total_small_individual", 0),
            "top_industries": wbmr.get("top_industries", []) if wbmr else [],
            "top_donors": wbmr.get("top_donors", []) if wbmr else [],
        },
        "votes": {
            "recent": votes[:10],
            "total_tracked": len(votes),
            "yea_count": yea_count,
            "nay_count": nay_count,
        },
        "sponsored_bills": sponsored,
        "promise_score": promise_score,
        "contact": {
            "phone": leg.get("phone", ""),
            "website": leg.get("website", ""),
            "office": leg.get("office", ""),
            "contact_form": leg.get("contact_form", ""),
        },
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
