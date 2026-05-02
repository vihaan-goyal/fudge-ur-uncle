"""Try alternate FTM endpoint paths."""
import asyncio, httpx
from config import FTM_API_KEY

NEEDLEMAN = 7109146

ENDPOINTS = [
    ("/sectors.php", {"eid": NEEDLEMAN}),
    ("/contributions.php", {"eid": NEEDLEMAN}),
    ("/breakdown.php", {"eid": NEEDLEMAN}),
    ("/industries.php", {"eid": NEEDLEMAN}),
    ("/aggregate.php", {"eid": NEEDLEMAN}),
    ("/candidate.php", {"eid": NEEDLEMAN}),
    # entity.php variants - try query types
    ("/entity.php", {"eid": NEEDLEMAN, "section": "industries"}),
    ("/entity.php", {"eid": NEEDLEMAN, "type": "AsCandidate"}),
    # Try supplying contributions-side filter on the bare endpoint
    ("/", {"dataset": "contributions", "gro": "s-x-bs", "f-y-fceid": NEEDLEMAN}),
    ("/", {"dataset": "contributions", "gro": "s-x-bs", "f-fceid": NEEDLEMAN}),
    ("/", {"dataset": "contributions", "gro": "s-x-bs", "r-eid": NEEDLEMAN}),
    ("/", {"dataset": "contributions", "gro": "s-x-bs", "f-y-celk": NEEDLEMAN}),
]

async def main():
    async with httpx.AsyncClient() as c:
        for path, params in ENDPOINTS:
            url = f"https://api.followthemoney.org{path}"
            full = {**params, "APIKey": FTM_API_KEY, "mode": "json"}
            try:
                r = await c.get(url, params=full, timeout=20)
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    d = r.json()
                    if isinstance(d, dict):
                        recs = d.get("records") or []
                        n = len(recs) if isinstance(recs, list) else "dict"
                        meta = d.get("metaInfo", {})
                        grouping = meta.get("grouping", {}).get("currentGrouping") if isinstance(meta, dict) else None
                        first = ""
                        if isinstance(recs, list) and recs and isinstance(recs[0], dict):
                            keys = [k for k in recs[0].keys() if k not in ("record_id","request")]
                            first = f" keys={keys[:5]}"
                        print(f"{path:25s} {str(params):60s} -> HTTP {r.status_code}, recs={n} grp={grouping}{first}")
                    else:
                        print(f"{path:25s} {str(params):60s} -> HTTP {r.status_code}, type={type(d).__name__}")
                else:
                    print(f"{path:25s} {str(params):60s} -> HTTP {r.status_code}, ct={ct!r} body[:80]={r.text[:80]!r}")
            except Exception as e:
                print(f"{path:25s} {str(params):60s} -> error: {type(e).__name__}: {str(e)[:60]}")

asyncio.run(main())
