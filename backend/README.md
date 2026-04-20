# Fudge Ur Uncle — Backend API

Politician accountability tracker. Aggregates campaign finance, voting records, and representative data from public sources into a single API.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the demo (works immediately with sample data)
python scripts/demo.py

# Start the API server
python server.py
# Visit http://localhost:8000/docs for interactive API docs
```

## API Keys (all free)

| Key | Get it from | What it unlocks |
|-----|-------------|-----------------|
| `DATA_GOV_API_KEY` | [api.data.gov/signup](https://api.data.gov/signup/) | OpenFEC + Congress.gov (one key for both) |
| `WHOBOUGHTMYREP_API_KEY` | [whoboughtmyrep.com/developers](https://whoboughtmyrep.com/developers) | Pre-processed industry attribution |
| `LEGISCAN_API_KEY` | [legiscan.com/legiscan](https://legiscan.com/legiscan) | State-level bill tracking |

Set them as environment variables:
```bash
export DATA_GOV_API_KEY=your_key_here
export WHOBOUGHTMYREP_API_KEY=your_key_here
```

The app works without keys using embedded sample data — add keys to get real data.

## Architecture

```
fudge-ur-uncle/
├── server.py              # FastAPI server — all endpoints
├── config.py              # API keys & settings
├── requirements.txt
├── api/
│   ├── legislators.py     # unitedstates/congress-legislators (GitHub)
│   ├── openfec.py         # OpenFEC — raw campaign finance (FEC filings)
│   ├── congress_gov.py    # Congress.gov — votes, bills, member info
│   └── whoboughtmyrep.py  # WhoBoughtMyRep — industry-attributed funding
└── scripts/
    └── demo.py            # Test all integrations
```

## Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/reps/by-state/{state}` | All federal reps for a state with funding |
| `GET /api/reps/search?q=name` | Search reps by name |
| `GET /api/profile/{bioguide_id}` | **Full profile**: bio + funding + votes (powers main screen) |
| `GET /api/funding/{bioguide_id}` | Detailed funding breakdown |
| `GET /api/funding/{bioguide_id}/industries` | Industry-level money with PAC hop tracing |
| `GET /api/votes/{bioguide_id}` | Voting record, filterable by category |
| `GET /api/bills/search?q=keyword` | Search bills |

## Data Sources

- **Legislators**: [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators) — open source, community-maintained
- **Campaign Finance**: [OpenFEC API](https://api.open.fec.gov/developers/) — official FEC data
- **Industry Attribution**: [WhoBoughtMyRep](https://whoboughtmyrep.com/developers) — traces money through PAC hops
- **Votes & Bills**: [Congress.gov API](https://api.congress.gov/) — official Library of Congress data
- **State Bills**: [LegiScan](https://legiscan.com/legiscan) — 50 states + Congress

## What's Next

- [ ] Promise tracking database (the differentiator — no API exists for this)
- [ ] Connect React frontend wireframe to these endpoints
- [ ] Add LegiScan for state-level vote tracking
- [ ] Add ProPublica Nonprofit Explorer for dark money / 990s
- [ ] Alert system: detect donation spikes before key votes
- [ ] User accounts + zip code → auto-match representatives
