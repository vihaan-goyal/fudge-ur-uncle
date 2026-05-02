"""Inspect the 'request' URLs FTM embeds inside entity.php — these reveal
the exact dataset+grouping+filter combo their own UI uses."""
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
    # Print every `request` URL embedded in the response
    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "request" and isinstance(v, str):
                    print(f"{path}.request = {v}")
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
    walk(data, "data")

    # Also dump the AsCandidate ContributionsTo section in full — that's where
    # "donations received by this candidate" lives.
    print("\n=== AsCandidate.ContributionsTo (full) ===")
    print(json.dumps(data.get("AsCandidate", {}).get("ContributionsTo", {}), indent=2)[:2000])

asyncio.run(main())
