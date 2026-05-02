import asyncio, httpx, json
from config import FTM_API_KEY

NEEDLEMAN = 7109146

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get(
            "https://api.followthemoney.org/entity.php",
            params={"eid": NEEDLEMAN, "APIKey": FTM_API_KEY, "mode": "json"},
            timeout=30,
        )
        d = r.json()
    data = d.get("data", {})
    for section in ("overview", "AsCandidate", "AsContributor"):
        print(f"\n=== {section} ===")
        sec = data.get(section, {})
        if isinstance(sec, dict):
            print(f"keys: {list(sec.keys())}")
            for k, v in sec.items():
                if isinstance(v, list):
                    print(f"  {k}: list len={len(v)}")
                    if v and isinstance(v[0], dict):
                        print(f"    first entry keys: {list(v[0].keys())}")
                        print(f"    first entry: {v[0]!r}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:8]}")
                else:
                    s = str(v)
                    print(f"  {k}: {s[:120]!r}")
        else:
            print(f"  type={type(sec).__name__}: {str(sec)[:200]}")

asyncio.run(main())
