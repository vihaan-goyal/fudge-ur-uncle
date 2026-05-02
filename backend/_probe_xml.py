"""Probe entity.php in XML mode (per the docs example) to see if more data is exposed."""
import asyncio, httpx
from config import FTM_API_KEY

NEEDLEMAN = 7109146

async def main():
    async with httpx.AsyncClient() as c:
        # XML mode — might surface fields the JSON adapter strips
        r = await c.get(
            "https://api.followthemoney.org/entity.php",
            params={"eid": NEEDLEMAN, "APIKey": FTM_API_KEY, "mode": "xml"},
            timeout=30,
        )
        body = r.text
        print(f"HTTP {r.status_code}, ct={r.headers.get('content-type')!r}, len={len(body)}")
        # Print first ~3500 chars to see structure
        print(body[:3500])
        print("\n...\n[last 1000]\n")
        print(body[-1000:])

asyncio.run(main())
