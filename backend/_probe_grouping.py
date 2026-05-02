"""Try plausible NIMP grouping codes for industry breakdown."""
import asyncio, httpx
from config import FTM_API_KEY

BASE = "https://api.followthemoney.org/"
NEEDLEMAN = 7109146  # CT state senator with $1.8M lifetime, good test subject

CANDIDATES = [
    "s-x-bs",  # state expenditures by business sector
    "p-x-bs",  # payee by business sector
    "b-x-bs",  # business sector self
    "s-x-bm",  # business main category
    "s-x-bc",  # business category
    "s-x-cc",  # what code currently uses
    "p-x-cc",  # payee × Catcode
    "c-x-bs",  # candidate × business sector
    "b-x-cc",  # business × Catcode
    "f-x-bs",  # filer × business sector
    "s-x-i",   # industry token guess
    "s-y-bs",
]

async def probe(client, gro):
    params = {"APIKey": FTM_API_KEY, "mode": "json", "gro": gro, "dataset": "candidates", "f-eid": NEEDLEMAN}
    try:
        r = await client.get(BASE, params=params, timeout=20)
        d = r.json()
    except Exception as e:
        return gro, f"error: {e}"
    grouping = d.get("metaInfo", {}).get("grouping", {}).get("currentGrouping")
    recs = d.get("records") or []
    n = len(recs) if isinstance(recs, list) else "?"
    sample = ""
    if isinstance(recs, list) and recs and recs[0] != "No Records" and isinstance(recs[0], dict):
        sample_rec = recs[0]
        # Show just the keys + the first non-record_id/request fields
        keys = [k for k in sample_rec.keys() if k not in ("record_id","request")]
        sample = f"keys={keys[:6]}"
    return gro, f"grouping={grouping} records={n} {sample}"

async def main():
    async with httpx.AsyncClient() as c:
        for gro in CANDIDATES:
            label, result = await probe(c, gro)
            print(f"{label:10s}  {result}")

asyncio.run(main())
