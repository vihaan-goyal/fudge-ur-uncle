"""Final probe: test the real industry-breakdown groupings d-cci / d-ccg / d-ccb
on contributions filtered by c-t-eid (donations TO this candidate)."""
import asyncio, httpx
from config import FTM_API_KEY

BASE = "https://api.followthemoney.org/"
NEEDLEMAN = 7109146

async def get(client, **params):
    full = {**params, "APIKey": FTM_API_KEY, "mode": "json"}
    r = await client.get(BASE, params=full, timeout=25)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

async def show(client, label, **params):
    print(f"\n=== {label} ===")
    print(f"params: {params}")
    st, d = await get(client, **params)
    if not isinstance(d, dict):
        print(f"non-dict resp: {str(d)[:200]}")
        return
    recs = d.get("records") or []
    paging = d.get("metaInfo", {}).get("paging", {})
    grp = d.get("metaInfo", {}).get("grouping", {}).get("currentGrouping")
    print(f"HTTP {st}, recs_returned={len(recs)} totalRecords={paging.get('totalRecords')} grouping={grp}")
    for r in recs[:8]:
        # Print compact representation
        if isinstance(r, dict):
            simplified = {}
            for k, v in r.items():
                if k in ("record_id", "request"):
                    continue
                if isinstance(v, dict):
                    # Pull the human-readable value
                    for vk, vv in v.items():
                        if vk != "token" and vk != "id":
                            simplified[k] = vv
                            break
                    else:
                        simplified[k] = str(v)[:60]
                else:
                    simplified[k] = v
            print(f"  {simplified}")

async def main():
    async with httpx.AsyncClient() as client:
        # Group donations to Needleman by general industry (d-cci)
        await show(client, "Needleman by Contributor General Industry (d-cci)",
                   dataset="contributions", gro="d-cci", **{"c-t-eid": NEEDLEMAN})
        # By broad sector (d-ccg)
        await show(client, "Needleman by Contributor Broad Sector (d-ccg)",
                   dataset="contributions", gro="d-ccg", **{"c-t-eid": NEEDLEMAN})
        # By specific business (d-ccb)
        await show(client, "Needleman by Contributor Specific Business (d-ccb)",
                   dataset="contributions", gro="d-ccb", **{"c-t-eid": NEEDLEMAN})
        # Also try with year filter
        await show(client, "Needleman by Industry, year=2022",
                   dataset="contributions", gro="d-cci", y=2022, **{"c-t-eid": NEEDLEMAN})
        # And verify state filter token is just 's'
        await show(client, "CT candidates 2022 (gro=c-t-id, s=CT)",
                   dataset="candidates", gro="c-t-id", s="CT", y=2022)

asyncio.run(main())
