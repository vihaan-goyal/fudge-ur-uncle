"""Use grouping to actually enumerate candidates. The bare /?dataset=candidates
returns a global summary — without a `gro` it doesn't break out rows.
Also test the contributions dataset with c-t-eid filter (the real filter for
'donations to this candidate'), and confirm which gro returns industry rows."""
import asyncio, httpx, json
from config import FTM_API_KEY

BASE = "https://api.followthemoney.org/"

async def get(client, **params):
    full = {**params, "APIKey": FTM_API_KEY, "mode": "json"}
    r = await client.get(BASE, params=full, timeout=25)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

async def main():
    async with httpx.AsyncClient() as client:
        # 1. Enumerate CT candidates in a recent cycle by grouping on candidate id
        print("=== CT candidates 2022, gro=c-t-id ===")
        st, d = await get(client, dataset="candidates", gro="c-t-id", **{"s-y-st": "CT", "y": 2022})
        if isinstance(d, dict):
            recs = d.get("records") or []
            paging = d.get("metaInfo", {}).get("paging", {})
            grouping = d.get("metaInfo", {}).get("grouping", {})
            print(f"HTTP {st}, recs={len(recs)}, paging={paging}, grouping={grouping}")
            for r in recs[:5]:
                print(f"  {r}")

        # 2. Try the same with no year — sometimes year filter is per-cycle and excludes off-cycle
        print("\n=== CT candidates all-years, gro=c-t-id ===")
        st, d = await get(client, dataset="candidates", gro="c-t-id", **{"s-y-st": "CT"})
        if isinstance(d, dict):
            recs = d.get("records") or []
            paging = d.get("metaInfo", {}).get("paging", {})
            print(f"HTTP {st}, recs={len(recs)}, paging={paging}")
            for r in recs[:5]:
                print(f"  {r}")

        # 3. Try the contributions dataset (donations) filtered by candidate-target-eid for Needleman
        print("\n=== contributions to Needleman (c-t-eid=7109146) gro=s-x-cc ===")
        st, d = await get(client, dataset="contributions", gro="s-x-cc", **{"c-t-eid": 7109146})
        if isinstance(d, dict):
            recs = d.get("records") or []
            print(f"HTTP {st}, recs={len(recs)}")
            for r in recs[:8]:
                print(f"  {r}")

        # 4. Same but for Needleman as donor (d-eid)
        print("\n=== contributions FROM Needleman (d-eid=7109146) gro=s-x-cc ===")
        st, d = await get(client, dataset="contributions", gro="s-x-cc", **{"d-eid": 7109146})
        if isinstance(d, dict):
            recs = d.get("records") or []
            print(f"HTTP {st}, recs={len(recs)}")
            for r in recs[:8]:
                print(f"  {r}")

asyncio.run(main())
