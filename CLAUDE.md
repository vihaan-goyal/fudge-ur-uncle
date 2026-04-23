# Fudge Ur Uncle

Politician accountability app. Tracks federal legislators, follows campaign donations through PAC hops, correlates them with upcoming votes, and surfaces alerts. Built as a mobile-first React frontend on top of a FastAPI backend.

## Repo Layout

```
fudge-ur-uncle-full/
├── backend/           # Python FastAPI server
│   ├── server.py      # entrypoint - all HTTP endpoints live here
│   ├── config.py      # API keys + settings (loads from .env)
│   ├── db.py          # SQLite schema + connection helpers
│   ├── data/whoboughtmyrep.sqlite   # local DB (gitignored)
│   ├── api/           # external API wrappers
│   │   ├── legislators.py        # unitedstates/congress-legislators (GitHub)
│   │   ├── openfec.py            # OpenFEC campaign finance
│   │   ├── congress_gov.py       # Congress.gov votes/bills
│   │   ├── whoboughtmyrep.py     # industry-attributed funding
│   │   ├── events.py             # Congress.gov committee meetings (two-phase fetch)
│   │   ├── news.py               # NewsAPI.org - US news article search (primary)
│   │   ├── guardian.py           # The Guardian API - news article search (fallback)
│   │   ├── ai_summary.py         # OpenAI GPT-4o-mini - plain-English event summaries
│   │   ├── stance_analysis.py    # OpenAI GPT-4o-mini - per-legislator policy stance analysis
│   │   └── alerts_router.py      # /api/alerts/* endpoints
│   └── alerts/        # alert generation pipeline
│       ├── config.py             # alert pipeline tuning (thresholds, lookback windows)
│       ├── industry_map.py       # industry <-> vote category topic-match table
│       ├── scoring.py            # signals-based alert scoring formula (T,V,D,R,A,N)
│       ├── ingest_fec.py         # pulls FEC donations into DB
│       ├── pac_classifier.py     # tags PACs by industry
│       ├── reclassify.py         # re-runs classifier on existing donation rows
│       ├── inspect_unknowns.py   # debug: lists top unclassified PACs
│       ├── debug_fec.py          # debug: probes FEC responses during ingest
│       ├── pipeline.py           # generates alerts from donations + votes
│       └── seed.py               # seed data for dev
└── frontend/          # React + Vite app
    ├── package.json
    ├── vite.config.js            # proxies /api -> localhost:8000
    └── src/
        ├── main.jsx              # entry
        ├── api.js                # fetch wrapper + endpoint methods
        └── App.jsx               # all 18 screens + routing (single file)
```

## Run Commands

Backend (terminal 1, from repo root):
```
cd backend
pip install -r requirements.txt
python server.py
# -> http://localhost:8000   (docs at /docs)
```

Frontend (terminal 2, from repo root):
```
cd frontend
npm install
npm run dev
# -> http://localhost:5173
```

Alerts pipeline (one-off, from repo root):
```
python -m backend.db                              # init schema
python -m backend.alerts.seed                     # seed legislators + scheduled votes
python -m backend.alerts.ingest_fec --state CT    # pull real FEC donations
python -m backend.alerts.pipeline                 # generate alerts
python -m backend.alerts.reclassify --only-unknown   # re-tag PACs after editing pac_classifier.py
```

## Environment

`backend/.env` should contain (all optional - missing keys fall back to sample data or DEMO_KEY):
- `DATA_GOV_API_KEY` - covers Congress.gov AND OpenFEC. Get one at api.data.gov/signup
- `NEWSAPI_KEY` - newsapi.org (free tier: 100 req/day). Primary news source for event detail screens. Aggregates AP, Reuters, Politico, The Hill, etc.
- `OPENAI_API_KEY` - openai.com. Powers AI plain-English summaries on event detail screens (uses gpt-4o-mini).
- `GUARDIAN_API_KEY` - The Guardian Open Platform. Free at open-platform.theguardian.com. Fallback news source if NewsAPI returns nothing.
- `WHOBOUGHTMYREP_API_KEY` - whoboughtmyrep.com/developers
- `LEGISCAN_API_KEY` - legiscan.com (state-level, not yet wired)

The health endpoint `GET /` reports which keys are configured.

## Architecture Notes

**Backend is a thin aggregator.** External APIs are wrapped in `backend/api/*.py`. `server.py` composes them into the unified shapes the frontend needs. Only the alerts subsystem persists to SQLite; everything else is fetched live.

**Frontend has graceful fallback baked in.** Every screen wraps API calls in a try/catch. If the backend is unreachable, it falls back to embedded sample data and shows an "OFFLINE" badge in the status bar. Do not remove this pattern - it's how the app stays demoable without a backend running.

**Dashboard uses lazy loading.** `/api/reps/by-state/{state}` returns reps with `funding: null`, then the frontend fires per-rep `/api/reps/{id}/funding-lite` calls. This keeps the initial render fast.

**The profile endpoint is the workhorse.** `/api/profile/{bioguide_id}` returns bio + funding + votes in one shot and powers most of the per-politician screens.

**Events use a two-phase fetch.** `GET /api/events` first fetches the Congress.gov `/v3/committee-meeting` list (summary stubs with URLs only), then fans out with `asyncio.gather` to fetch up to 10 detail URLs in parallel. The list endpoint does not return title/date/location — only the detail endpoint does. Results are cached in-process for 5 minutes. See `backend/api/events.py`.

**Event detail screen fetches news and AI summary lazily.** Two on-demand calls fire when the user opens an event detail:
- `GET /api/events/article?q={title}` — searches NewsAPI.org first (primary), falls back to Guardian if no results. Requires `NEWSAPI_KEY`; returns `{"article": null}` if both keys are missing.
- `GET /api/events/summary?title=...&chamber=...&meeting_type=...&committee=...&bills=...` — calls OpenAI GPT-4o-mini to generate a 2-sentence plain-English citizen briefing. Requires `OPENAI_API_KEY`; returns `{"summary": null}` if missing. Results are cached in-process by event title to avoid repeated API calls.

**News query extraction** (`backend/api/news.py` and `guardian.py`) strips congressional boilerplate from hearing titles to build focused search queries — pulls topic after `:` or `on`, extracts named acts from markups, appends "Congress" if no political signal word present.

**Stance analysis is AI-derived from real votes.** `GET /api/profile/{bioguide_id}/stances` pulls the legislator's recent votes + sponsored bills and asks GPT-4o-mini to identify 4-6 policy areas with a `topic`/`stance`/`evidence`/`score` shape (CONSISTENT, INCONSISTENT, MIXED, PENDING). Requires `OPENAI_API_KEY`; returns `{"stances": null, "ai_available": false}` if missing. Cached in-process per bioguide_id. See `backend/api/stance_analysis.py`.

**Alert scoring is a documented formula, not a heuristic.** `backend/alerts/scoring.py` computes `S = (T*V) * (alpha*D + beta*R + gamma*A) * (1 + delta*N)` where T=topic match, V=vote proximity, D=donation magnitude, R=recency, A=anomaly z-score, N=news salience. Topic match uses the table in `industry_map.py`. Thresholds: S>0.3 → alert, S>0.6 → urgent. All intermediate signals are stored on the alert for explainability.

## Conventions

- Backend: `async`/`await` everywhere, `httpx.AsyncClient` for outbound calls, retry with exponential backoff on 429s.
- All endpoints return JSON with consistent shapes. Add new ones to `server.py` next to similar existing endpoints.
- New external APIs go in `backend/api/` as their own module, then composed in `server.py`.
- Frontend is intentionally a single `App.jsx` file - all 18 screens, styles via inline `style={s.foo}` objects against a shared `s` style map. Don't split this up casually; the single-file structure was a deliberate choice.
- Frontend screens are switched via a `currentScreen` state + `SCREENS` enum, not React Router.

## Gotchas

- `python -m backend.alerts.pipeline` must run from the **project root**, not from inside `backend/`. The package imports rely on it.
- `backend/data/whoboughtmyrep.sqlite` is created on first run of `python -m backend.db`. The `/api/alerts/*` endpoints will 503 until that and the pipeline have run.
- Vite proxies `/api/*` to `localhost:8000`, so don't add `http://localhost:8000` prefixes in frontend fetches - just use `/api/...`.
- For production frontend builds, set `VITE_API_BASE=https://your-backend.example.com` before `npm run build`.
- The OpenFEC `candidate -> principal committee` resolution is fuzzy. See `get_principal_committee` in `ingest_fec.py` for the fallback chain (try scoped cycle, then unscoped, then committee lookup by candidate_id).

## Status (April 2026)

Wired and live: dashboard, search, profile, funding, voting history, timeline, take-action, contact reps, settings, alerts (when pipeline has run), events + event detail (real Congress.gov committee meetings, NewsAPI news articles, OpenAI plain-English summaries), AI stance analysis on profile screen (when `OPENAI_API_KEY` is set).

Still placeholder / sample data only: promise scoring.