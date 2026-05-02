"""Find a state-legislator eid that actually has candidate-side donation data,
then probe the contributions dataset for an industry breakdown.

Strategy: search for well-known CT state senate/house members, fetch their
entity.php, pick one whose AsCandidate.ContributionsTo has Num_of_Records > 0,
then try various 'gro' codes against the contributions dataset filtered by
c-t-eid to find which one actually returns industry rows."""
import asyncio, httpx, json
from config import FTM_API_KEY

NAMES = [
    # CT state senate / house — public figures, should have candidate-side data
    "Looney, Martin",
    "Ritter, Matthew",
    "Duff, Bob",
    "Lamont, Ned",  # governor — should be in FTM
    "Murphy, Chris",  # US senator from CT, definitely has data
]

async def search(client, name):
    """Use FTM candidate search to find an eid by name."""
    params = {
        "APIKey": FTM_API_KEY,
        "mode": "json",
        "search": name,
        "dataset": "candidates",
    }
    r = await client.get("https://api.followthemoney.org/", params=params, timeout=20)
    d = r.json()
    return d.get("records") or []

async def get_entity(client, eid):
    r = await client.get(
        "https://api.followthemoney.org/entity.php",
        params={"eid": eid, "APIKey": FTM_API_KEY, "mode": "json"},
        timeout=20,
    )
    return r.json()

async def main():
    async with httpx.AsyncClient() as client:
        print("=== Step 1: search for known names ===")
        for name in NAMES:
            try:
                recs = await search(client, name)
                print(f"\n'{name}': {len(recs)} records")
                for r in recs[:5]:
                    keys = {k: v for k, v in r.items() if k not in ("record_id", "request")}
                    print(f"  {keys}")
            except Exception as e:
                print(f"'{name}': error {e!r}")

asyncio.run(main())
