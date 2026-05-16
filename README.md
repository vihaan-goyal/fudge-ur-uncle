# Fudge Ur Uncle

Politician accountability app. Tracks federal + state legislators, follows campaign donations, correlates them with upcoming votes, and surfaces alerts when a rep's funders have money riding on a bill that's about to hit the floor.

Mobile-first React PWA on a FastAPI backend. Installable on iOS/Android from the browser.

## What's Inside

```
fudge-ur-uncle-full/
├── backend/      # FastAPI + SQLite. External APIs wrapped per-module, composed in server.py.
│   ├── api/      # legislators, openfec, congress_gov, whoboughtmyrep, legiscan, ftm, news,
│   │             # guardian, ai_summary, stance_analysis, promises, assistant_chat, alerts_*…
│   └── alerts/   # ingest (federal + state), scoring, pipeline, refresh entrypoint
└── frontend/     # React + Vite. 24 screens in one App.jsx by design. PWA via manifest + sw.js.
```

## Run It

Two terminals, from the project root:

```bash
# Backend (port 8000)
cd backend
pip install -r requirements.txt
python -m backend.db                       # init schema — first run only
python server.py

# Frontend (port 5173)
cd frontend
npm install
npm run dev
```

Vite proxies `/api/*` to `localhost:8000`, so no CORS config needed in dev. Open http://localhost:5173.

### Populate alerts (optional)

The alerts pipeline needs ingested donations + upcoming votes before it has anything to score:

```bash
python -m backend.alerts.refresh           # federal ingest → state ingest → pipeline
# flags: --states CT --skip-federal --skip-state --congress 119
```

Run this from the project root, not from inside `backend/`. `/api/alerts/*` returns 503 until the pipeline has populated.

> Don't mix `seed.py` and `refresh` on the same DB — refresh's ingest purges seeded rows that aren't in the live keepers list. Pick one source.

### Tests

```bash
cd backend && python -m pytest tests/ -v    # 193 tests: smoke, pipeline, classifier, categories, etc.
cd frontend && npm test                     # vitest — currently covers groupAlerts only
```

Tests use `FUU_DB_PATH` (set by conftest) so they don't clobber dev data.

## API Keys

All optional — missing keys fall back to sample data or `DEMO_KEY`. Put them in `backend/.env`:

| Key | Source | What it unlocks |
|-----|--------|------------------|
| `DATA_GOV_API_KEY` | [api.data.gov/signup](https://api.data.gov/signup/) | Congress.gov + OpenFEC (one key, both APIs) |
| `OPENAI_API_KEY` | platform.openai.com | gpt-4o-mini for stances, promises, event summaries, Mamu chat, category fallback |
| `NEWSAPI_KEY` | newsapi.org | Primary news source for event detail (100 req/day free) |
| `GUARDIAN_API_KEY` | open-platform.theguardian.com | Fallback news source |
| `WHOBOUGHTMYREP_API_KEY` | [whoboughtmyrep.com/developers](https://whoboughtmyrep.com/developers) | Industry-attributed funding (PAC hop tracing) |
| `LEGISCAN_API_KEY` | [legiscan.com/legiscan](https://legiscan.com/legiscan) | State legislators (30k/mo, 1 req/sec, cached) |
| `FTM_API_KEY` | followthemoney.org | State campaign finance (NIMP) |

`GET /` reports which of the 7 keys are configured — Settings reads this to render the "Keys configured" list.

## Features

- **Auth** — bcrypt + opaque 30-day session tokens, per-IP/email throttle, constant-time login. Plus a temporary "Continue as guest" affordance on the login screen for demos.
- **Dashboard** — orientation surface for new voters/immigrants. Greeting, quick actions, "Coming up" (state-scoped upcoming votes, personalized to your issues), your reps with lazy-loaded funding.
- **Search** — unified federal (GitHub roster) + state (Legiscan), one query string, results tagged by level. Lives as a top-right icon on the Dashboard.
- **Politician profile** — bio + funding breakdown + voting record + timeline + take action + contact. One endpoint (`/api/profile/{bioguide_id}`) fans out ~5 upstream calls, cached 6h.
- **AI stances + promises** — gpt-4o-mini analyzes votes + sponsored bills (stances) and scraped `.gov`/Wikipedia/Ballotpedia copy (promises). Works for federal and state reps.
- **Events** — Congress.gov committee meetings with parallel detail fetch, NewsAPI/Guardian news, 2-sentence AI summaries. Past meetings filtered out, soonest first.
- **Alerts** — server pipeline scores `(donation × upcoming vote)` pairs, frontend collapses by `(actor, industry, category)`. Federal + state, urgent threshold at `S > 0.6`. State path calibrated separately because FTM donations are lifetime-stamped.
- **Mamu** — civics tutor chatbot. Dedicated bottom-nav tab (sparkle icon) plus a floating pill on every signed-in screen. Context-aware: reads cached profile/bill data to ground answers; multi-turn memory; 24h response cache.
- **Settings** — edit state + issues (drives Dashboard personalization), see which API keys the backend has, sign out, delete account (re-auth required).

## Architecture Highlights

- **Backend is a thin aggregator.** External APIs wrapped per-module; `server.py` composes. Only the alerts subsystem persists to SQLite — everything else is live-fetched with in-process + `ai_cache` caching.
- **Frontend stays single-file.** All 24 screens live in `App.jsx`. Routing via `currentScreen` state + a `SCREENS` enum, not React Router. Two narrow extractions: `groupAlerts.js` (unit-tested) and `copy.js` (centralized user-facing strings — single swap-point for tone).
- **Graceful offline.** Every API call wraps try/catch and falls back to embedded sample data with an "OFFLINE" badge. The app stays demoable with zero keys, zero backend.
- **PWA with iOS quirks handled.** Manifest + service worker pre-cache the app shell; `/api/*` deliberately bypassed so live data never staleness-pins. PWA mode has its own render path (no dev chrome, full-bleed phone frame, body-lock to kill iOS rubber-band).
- **Two-tier cache for AI + Legiscan.** Persistent SQLite `ai_cache` (namespaced keys, per-key TTLs from 15 min to 30 days) sits behind a few in-process caches. Wipe poisoned rows directly when fixing parsers — TTLs pin bad data.

See `CLAUDE.md` for the long-form tour: scoring formula, schema, ingest quirks (FEC ID order, FTM EID directory, Legiscan chamber/rate-limit gotchas), motion conventions, PWA gotchas, and deploy notes.

## Deploy

**Frontend → Vercel.** `vercel.json` pins SPA rewrites + `Cache-Control: no-cache` on `/sw.js`. Set `VITE_API_BASE=https://your-backend-url` in Vercel's Production env *before* building — Vite inlines `import.meta.env.*` at build time, not runtime.

**Backend → Railway / Render / Fly / Heroku.** `Procfile` is `web: uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}`. Persistent disk required (SQLite at `backend/data/whoboughtmyrep.sqlite` — Vercel functions and Render free tier lose it on redeploy). `refresh.py` is the cron entrypoint.

CORS is `allow_origins=["*"]` — fine for read-only, tighten if the surface changes.

## Status

Everything above is wired and live. Test suite is 193 tests; classifier, pipeline scoring, state-calibration anchor, vote-index, promise fallbacks, and upcoming-votes personalization all have coverage.

Deferred: live FTM EID lookup (workaround is the curated `backend/data/ftm_eids.csv`), email verification, password reset.
