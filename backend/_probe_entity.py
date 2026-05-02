"""Try entity.php and the contributions dataset for industry breakdown."""
import asyncio, httpx, json
from config import FTM_API_KEY

NEEDLEMAN = 7109146

async def probe(client, label, url, params):
    print(f"\n--- {label} ---")
    print(f"GET {url} params={params}")
    try:
        r = await client.get(url, params={**params, "APIKey": FTM_API_KEY, "mode": "json"}, timeout=25)
        print(f"HTTP {r.status_code}, ct={r.headers.get('content-type')!r}")
        try:
            d = r.json()
        except Exception:
            print(f"body[:500]: {r.text[:500]!r}")
            return
        if isinstance(d, dict):
            print(f"top keys: {list(d.keys())[:12]}")
            # entity.php often returns wrapping like {"entityResult": {...}}
            for k, v in d.items():
                if isinstance(v, dict):
                    print(f"  {k}: subkeys={list(v.keys())[:10]}")
                    if "industries" in v or "industry" in v:
                        print(f"    INDUSTRY data found under {k}")
                elif isinstance(v, list):
                    print(f"  {k}: list len={len(v)}")
        elif isinstance(d, list):
            print(f"list len={len(d)}")
        else:
            print(f"type {type(d).__name__}: {str(d)[:300]}")
    except Exception as e:
        print(f"error: {e!r}")

async def main():
    async with httpx.AsyncClient() as c:
        # Endpoint mentioned in NIMP docs example
        await probe(c, "entity.php for Needleman",
                    "https://api.followthemoney.org/entity.php",
                    {"eid": NEEDLEMAN})

        # Contributions dataset with various groupings
        for gro in ["b-x-bs", "s-x-bs", "p-x-bs", "s-x-cc", "f-x-bs"]:
            await probe(c, f"contributions dataset gro={gro}",
                        "https://api.followthemoney.org/",
                        {"dataset": "contributions", "gro": gro, "c-t-eid": NEEDLEMAN})

        # Try filing-based breakdown — Need to confirm what dataset returns industry rows
        await probe(c, "candidates without f-eid (sanity, see grouping shape)",
                    "https://api.followthemoney.org/",
                    {"dataset": "candidates", "gro": "s-x-bs", "s": "CT", "y": 2024})

asyncio.run(main())
