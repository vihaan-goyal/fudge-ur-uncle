"""
Fudge Ur Uncle - Demo Script
==============================
Run this to test all API integrations.
Works with sample data out of the box,
connects to real APIs when keys are configured.

Usage:  python scripts/demo.py
"""

import asyncio
import json
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import legislators, openfec, congress_gov, whoboughtmyrep
import config


def pp(label: str, data, max_items: int = 3):
    """Pretty print a section."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, list):
        for item in data[:max_items]:
            print(json.dumps(item, indent=2, default=str))
        if len(data) > max_items:
            print(f"  ... and {len(data) - max_items} more")
    elif isinstance(data, dict):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


async def main():
    print("\n" + "=" * 60)
    print("  FUDGE UR UNCLE - API Integration Demo")
    print("=" * 60)

    print(f"\n  API Keys:")
    print(f"    data.gov:        {'configured' if config.DATA_GOV_API_KEY != 'DEMO_KEY' else 'DEMO_KEY (rate limited)'}")
    print(f"    WhoBoughtMyRep:  {'configured' if config.WHOBOUGHTMYREP_API_KEY else 'not set (using samples)'}")
    print(f"    LegiScan:        {'configured' if config.LEGISCAN_API_KEY else 'not set'}")

    # ---- 1. Legislators ----
    print("\n\n[1/5] LEGISLATORS (unitedstates/congress-legislators)")
    print("-" * 50)

    ct_reps = await legislators.search_by_state("CT")
    pp("CT Representatives", ct_reps)

    murphy = await legislators.search_by_name("Murphy")
    pp("Search: 'Murphy'", murphy)

    # ---- 2. OpenFEC ----
    print("\n\n[2/5] OPENFEC (campaign finance)")
    print("-" * 50)

    # Use Murphy's FEC ID
    fec_id = "S8CT00177"
    totals = await openfec.get_candidate_totals(fec_id)
    pp(f"Candidate Totals: {fec_id}", totals)

    contributors = await openfec.get_top_contributors(fec_id, limit=5)
    pp(f"Top Contributors: {fec_id}", contributors, 5)

    # ---- 3. Congress.gov ----
    print("\n\n[3/5] CONGRESS.GOV (votes & bills)")
    print("-" * 50)

    votes = await congress_gov.get_member_votes("M001169")
    pp("Murphy's Votes", votes)

    bills = await congress_gov.search_bills("infrastructure")
    pp("Bill Search: 'infrastructure'", bills)

    # ---- 4. WhoBoughtMyRep ----
    print("\n\n[4/5] WHOBOUGHTMYREP (industry attribution)")
    print("-" * 50)

    wbmr_ct = await whoboughtmyrep.get_reps(state="CT")
    pp("CT Reps (with funding)", wbmr_ct)

    if wbmr_ct:
        rep = wbmr_ct[0]
        pp(f"Top Industries: {rep.get('name', 'Unknown')}", rep.get("top_industries", []))
        pp(f"Top Donors: {rep.get('name', 'Unknown')}", rep.get("top_donors", []))

    # ---- 5. Composite Profile ----
    print("\n\n[5/5] COMPOSITE PROFILE (all sources merged)")
    print("-" * 50)

    leg = await legislators.get_by_bioguide("M001169")
    if leg:
        fec_ids = leg.get("fec_ids", [])
        fec_totals = await openfec.get_candidate_totals(fec_ids[0]) if fec_ids else {}

        profile = {
            "name": leg["name"],
            "party": leg["party"],
            "state": leg["state"],
            "district": leg["district"],
            "chamber": leg["chamber"],
            "phone": leg["phone"],
            "website": leg["website"],
            "total_raised": fec_totals.get("total_receipts", "N/A"),
            "pac_money": fec_totals.get("total_pac_contributions", "N/A"),
            "individual_money": fec_totals.get("total_individual_contributions", "N/A"),
            "recent_votes": len(votes),
        }
        pp("Full Profile: Sen. Chris Murphy (CT)", profile)

    # ---- Summary ----
    print("\n\n" + "=" * 60)
    print("  DEMO COMPLETE")
    print("=" * 60)
    print("""
  Data sources tested:
    [x] Legislators (GitHub/unitedstates)
    [x] Campaign Finance (OpenFEC)
    [x] Voting Records (Congress.gov)
    [x] Industry Attribution (WhoBoughtMyRep)

  To connect real APIs, set environment variables:
    export DATA_GOV_API_KEY=your_key        # https://api.data.gov/signup/
    export WHOBOUGHTMYREP_API_KEY=your_key  # https://whoboughtmyrep.com/developers

  To run the server:
    cd fudge-ur-uncle
    python server.py
    # Then visit http://localhost:8000/docs
    """)


if __name__ == "__main__":
    asyncio.run(main())
