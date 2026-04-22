"""
Debug script to figure out why fetch_pac_contributions returns 0 records.

Tries 4 different query variants against Blumenthal's committee (C00492991)
and prints the result counts. This narrows down which filter is too strict.

Run from project root:
    python -m backend.alerts.debug_fec
"""

import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import httpx
import config  # type: ignore


COMMITTEE_ID = "C00492991"  # Blumenthal "Friends of Dick Blumenthal" - confirmed real


async def try_query(client, label: str, params: dict) -> None:
    """Run one query and report what came back."""
    full = {**params, "api_key": config.DATA_GOV_API_KEY,
            "committee_id": COMMITTEE_ID, "per_page": 5}
    url = f"{config.OPENFEC_BASE}/schedules/schedule_a/"
    print(f"\n--- {label} ---")
    print(f"  params: {params}")
    try:
        resp = await client.get(url, params=full, timeout=30)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
            return
        data = resp.json()
        results = data.get("results", [])
        pagination = data.get("pagination", {})
        total = pagination.get("count", "?")
        print(f"  total available: {total}")
        print(f"  returned this page: {len(results)}")
        for r in results[:3]:
            print(f"    - {r.get('contribution_receipt_date', '?')[:10]}  "
                  f"${r.get('contribution_receipt_amount', 0):>10,.2f}  "
                  f"{r.get('contributor_name', '?')[:50]}")
    except Exception as e:
        print(f"  ERROR: {e!r}")


async def main():
    print(f"[debug] Using API key: "
          f"{'DEMO_KEY' if config.DATA_GOV_API_KEY == 'DEMO_KEY' else 'real key set'}")
    print(f"[debug] Testing committee: {COMMITTEE_ID}")

    async with httpx.AsyncClient() as client:
        # 1. Bare query: no filters at all
        await try_query(client, "BARE - no filters", {})

        # 2. Just contributor_type=committee
        await try_query(client, "PAC contributions only",
                        {"contributor_type": "committee"})

        # 3. PAC + cycle 2026
        await try_query(client, "PAC + cycle 2026",
                        {"contributor_type": "committee",
                         "two_year_transaction_period": 2026})

        # 4. PAC + cycle 2024 (last full cycle)
        await try_query(client, "PAC + cycle 2024 (previous)",
                        {"contributor_type": "committee",
                         "two_year_transaction_period": 2024})

        # 5. PAC + min_date in ISO format
        await try_query(client, "PAC + min_date ISO",
                        {"contributor_type": "committee",
                         "min_date": "2026-01-01"})

        # 6. PAC + min_date in MM/DD/YYYY format
        await try_query(client, "PAC + min_date MM/DD/YYYY",
                        {"contributor_type": "committee",
                         "min_date": "01/01/2026"})

        # 7. The exact query our pipeline uses
        await try_query(client, "EXACT pipeline query",
                        {"contributor_type": "committee",
                         "two_year_transaction_period": 2026,
                         "min_date": "2026-01-21",
                         "sort": "-contribution_receipt_date"})


if __name__ == "__main__":
    asyncio.run(main())