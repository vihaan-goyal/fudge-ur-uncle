# Fudge Ur Uncle

Politician accountability app. Tracks federal + state legislators, follows campaign donations, correlates them with upcoming votes, and surfaces alerts. Mobile-first React frontend on FastAPI backend, deployed as a Vercel PWA + Procfile-based backend host.

## Repo Layout

```
backend/
  server.py          # FastAPI entrypoint, all HTTP endpoints
  config.py          # API keys + HOST/PORT from .env
  db.py              # SQLite schema, migrations, connection helper
  Procfile           # web: uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
  data/whoboughtmyrep.sqlite   # local DB (gitignored)
  api/               # external API wrappers (one module per upstream)
    legislators.py openfec.py congress_gov.py whoboughtmyrep.py
    events.py news.py guardian.py ai_summary.py
    stance_analysis.py promises.py ai_cache.py
    legiscan.py state_sites.py followthemoney.py ftm_directory.py
    auth.py alerts_router.py
  alerts/            # alert generation pipeline
    config.py industry_map.py scoring.py catcode_map.py
    ingest_fec.py ingest_ftm.py ingest_federal_votes.py ingest_state_votes.py
    pac_classifier.py reclassify.py state_categories.py
    pipeline.py refresh.py seed.py
  data/ftm_eids.csv  # curated (state, chamber, name, eid) directory
  tests/             # pytest smoke + pipeline + classifier
frontend/
  vite.config.js     # proxies /api -> localhost:8000
  vercel.json        # SPA rewrites, no-cache on /sw.js
  public/            # manifest.webmanifest, sw.js, icons
  src/
    main.jsx api.js
    App.jsx          # all 23 screens + routing in one file (deliberate)
```

## Run Commands

From project root (imports require it):

```
# Backend
cd backend && pip install -r requirements.txt && python server.py     # :8000
# Frontend
cd frontend && npm install && npm run dev                              # :5173
# Pipeline (one-off)
python -m backend.db                       # init schema, first run only
python -m backend.alerts.refresh           # cron entrypoint: federal+state ingest then pipeline
# Tests
cd backend && python -m pytest tests/ -v
```

`refresh` chains `ingest_federal_votes` → `ingest_state_votes` (default `CT,NY,NJ,CA,MA`) → `pipeline`. Flags: `--states CT`, `--skip-federal`, `--skip-state`, `--congress 119`. Ingester failures log but don't block; only a pipeline crash exits non-zero.

Don't run `seed.py` and `refresh` against the same DB — `refresh`'s ingest purges scheduled-vote rows not in the live keepers list, including seeded ones. Pick one source.

Tests use `FUU_DB_PATH` (set by conftest) so they don't clobber dev data.

## Environment

`backend/.env` (all optional — missing keys fall back to sample data or DEMO_KEY):

- `DATA_GOV_API_KEY` — Congress.gov + OpenFEC (api.data.gov/signup)
- `OPENAI_API_KEY` — gpt-4o-mini for stances, promises, event summaries
- `NEWSAPI_KEY` — primary news source for event detail (100 req/day free)
- `GUARDIAN_API_KEY` — fallback news source
- `WHOBOUGHTMYREP_API_KEY` — industry-attributed funding
- `LEGISCAN_API_KEY` — state legislators (30k/mo + 1 req/sec, cached in `ai_cache`)
- `FTM_API_KEY` — FollowTheMoney/NIMP state campaign finance

`GET /` reports configured keys.

## Architecture

**Backend is a thin aggregator.** External APIs wrapped in `backend/api/*.py`; `server.py` composes them. Only the alerts subsystem persists to SQLite — everything else is fetched live with in-process caching.

**Frontend has graceful fallback.** Every screen wraps API calls in try/catch and falls back to embedded sample data with an "OFFLINE" badge. Don't remove — it's how the app stays demoable. `apiRequest` auto-clears localStorage on 401 (only when a token was actually sent), preventing dead-token retry loops.

**Single-file frontend.** `App.jsx` holds all 23 screens. Inline `style={s.foo}` against a shared `s` map. Screen routing via `currentScreen` state + `SCREENS` enum, not React Router. Don't split casually.

**Alerts are grouped client-side.** Pipeline writes one row per (donation × vote) pair, so a single donor in one category produces N near-identical cards (same headline, only bill differs). `groupAlerts()` in `App.jsx` collapses by `(actor_id, industry, category)`, takes the highest-scoring row as the lead, and rolls the rest into a bill list ("N upcoming {category} bills · $X lifetime" + first 3 bills + "(+K more)"). Both `AlertsScreen` and `StateRepAlertsScreen` use it. Singleton groups (or `SAMPLE.alerts` rows missing `donation`/`vote` fields) render the original body unchanged.

**Profile endpoint is the workhorse.** `/api/profile/{bioguide_id}` returns bio + funding + votes in one shot. Dashboard uses lazy loading: `/api/reps/by-state/{state}` returns reps with `funding: null`, frontend fans out per-rep `/api/reps/{id}/funding-lite` calls.

**Events use a two-phase fetch.** `/api/events` fetches the Congress.gov committee-meeting list (URL stubs only), then `asyncio.gather`s up to 10 detail URLs in parallel. Title/date/location only come from detail. 5-min in-process cache. Event detail lazily fetches news (`/article` — NewsAPI primary, Guardian fallback) and AI summary (`/summary` — gpt-4o-mini, 2-sentence brief). `news.py`/`guardian.py` strip congressional boilerplate to build focused queries.

**AI features (stances, promises) require `OPENAI_API_KEY`.** Stances pull recent votes + sponsored bills, GPT identifies 4–6 policy areas with CONSISTENT/INCONSISTENT/MIXED/PENDING scores. Promises scrape the rep's `.gov` site (homepage + `/issues`, `/priorities`, `/about`, parallel `asyncio.gather`, 14k char cap), then GPT extracts stated positions and labels each KEPT/BROKEN/PARTIAL/UNCLEAR. Returns `{scraped: false}` if scraping yielded <400 chars (common for JS-rendered sites). Substantive-vote filtering shared via `is_substantive_vote()` in `congress_gov.py`.

**Unified search.** `/api/search/unified?q=...&state=CT` fans out to federal (GitHub roster) and state (cached Legiscan roster) in parallel; results tagged `level: "federal" | "state"` so the frontend routes to the right profile screen.

**State legislators come from Legiscan.** Two-step roster fetch (`getSessionList` → newest → `getSessionPeople`), profile via `getPerson` + `getSponsoredList`. State deep-dive endpoints (`/votes`, `/stances`, `/promises`) mirror federal; promises uses Ballotpedia URLs from `state_sites.derive_website()`. Votes endpoint only finds rolls on bills the rep *sponsored* — backbenchers look thin.
- **Legiscan gotcha:** `getSponsoredList` returns flat `sponsoredbills.bills` with `session_id` per item; `sponsoredbills.sessions` is metadata, not nested bills. Sort by `session_id` desc.
- **Rate-limit gotcha:** `_call` serializes through a process-wide lock with 1.05s spacing so `asyncio.gather` fan-outs stay under 1 req/sec free-tier limit. Cold-cache votes fetches run ~16s; don't remove without a paid-tier flag.
- **Chamber gotcha:** Legiscan normalizes any lower-chamber `role` to `chamber: "House"` even in Assembly states (NY/NJ/CA), so CSV rows must use "House", not "Assembly".

**AI + Legiscan results cached in SQLite (`ai_cache.py`).** Keys are namespaced: `promises:{id}`, `stances:{id}`, `promises:state:{pid}`, `stances:state:{pid}`, `legiscan:people:{state}` (7d), `legiscan:profile:{pid}` (24h), `legiscan:votes:{pid}` (24h). Table created lazily; surviving server restarts. **Cache-bust gotcha:** poisoned entries stick for the TTL — wipe rows from `ai_cache` directly when fixing parsers.

**Alert scoring formula.** `scoring.py`: `S = (T*V) * (αD + βR + γA) * (1 + δN)` where T=topic match, V=vote proximity, D=donation magnitude, R=recency, A=anomaly z-score, N=news salience. `S>0.3` → alert, `S>0.6` → urgent. All signals stored on the alert for explainability.

**Alerts schema is polymorphic.** `donations`/`alerts`/`industry_baselines` key on `(actor_type, actor_id)` — `'federal'` (bioguide) or `'state'` (Legiscan people_id). `scheduled_votes` keys `(jurisdiction, state_code, bill_number)` so a CT bill and an NJ bill with the same number don't collide. Migrations in `db._migrate()` handle legacy DBs in place (table-swap idiom for PK/UNIQUE changes, runs *before* `executescript(SCHEMA)`). The `/api/alerts` endpoint accepts both `actor_type`/`actor_id` and legacy `bioguide_id` (auto-mapped to federal); responses include both fields.

**External IDs in a join table.** `external_ids(actor_type, actor_id, source, external_id, confidence, matched_at)` maps actors to FTM/OpenSecrets/FEC IDs. Adding a new data source doesn't churn the schema.

**Alerts carry `created_at` + `updated_at`.** `updated_at` is bumped on each pipeline re-confirmation so re-confirmed alerts read as fresh. Router compares against `datetime.now(timezone.utc).replace(tzinfo=None)` because SQLite's `CURRENT_TIMESTAMP` is UTC-naive — using `datetime.now()` skews relative-time strings by the local-UTC offset.

**State donations come from FTM lifetime aggregates, not itemized rows.** `ingest_ftm.py` per-actor loop: cached Legiscan roster → resolve eid → fetch industry breakdown via `dataset=contributions&gro=d-cci&c-t-eid=<EID>` → translate via `catcode_map.industry_for_ftm_name` (drops `_ignore` buckets) → write one `donations` row per industry tagged `actor_type='state'`. `donation_date = today` because FTM grouped aggregates are lifetime-only (year filters return 0 records when combined with grouping). Keeps rows inside the 180-day lookback. Dedup key: `FTM:{eid}:lifetime:{industry_slug}`.
- **Connection gotcha:** holding `with connect()` across `await`s starves `ai_cache` writes and triggers SQLite "database is locked." Open per-actor.
- **EID lookup uses an offline directory.** Live `_live_find_eid` is a stub — FTM's candidates-dataset state filter is undocumented and none of `s-y-st`, `s`, `c-r-s`, `c-t-s`, `c-r-osj` honor it empirically. Workaround: `backend/data/ftm_eids.csv` (loaded by `ftm_directory.py`), curated `(state, chamber, name, eid)` rows consulted before live and before `SAMPLE_FTM_EIDS`. Fuzzy match (SequenceMatcher ≥ 0.78) with chamber as disambiguator. Adding mappings is manual: look up on followthemoney.org, copy eid from URL, append CSV row. `site:followthemoney.org "LASTNAME, FIRSTNAME"` is the most reliable Google query (FTM's title format).
- **Cache pollution gotcha:** test runs that misconfigure `db.DB_PATH` will write `[]` sentinels to production `ai_cache`. If FTM matches stop returning, wipe rows where `cache_key LIKE 'ftm:%'`.
- **Quota gotcha:** FTM free tier returns HTTP 200 with `{"error": "...account has reached its free API call limit..."}`. `_ftm_get` raises `FTMUpstreamError`; `get_industry_aggregates` catches it, returns sample data for *just that call*, and does NOT cache. So a transient quota hiccup doesn't pin demo numbers under the live key for 24h.

**Upcoming-vote feeds use bill-status as a proxy** (no clean upstream calendar exists for either jurisdiction).
- State (`ingest_state_votes.py`): Legiscan masterlist filtered to `STATUS_ENGROSSED`. **Title-only categorization** via `state_categories.py` keyword regex (13 categories: environment, healthcare, economy, defense, infrastructure, technology, labor, agriculture, housing, education, immigration, firearms, elections). Description fallback was removed — long policy summaries produced too many incidental matches. Uncategorized bills (~25%) silently dropped at ingest. No per-bill `getBill` (would burn the 30k/mo quota). Masterlist cached 6h.
- Federal (`ingest_federal_votes.py`): `/v3/bill/{congress}` sorted `updateDate+desc`, paginated 4×250, filtered to `latestAction.text` matching `_FLOOR_IMMINENT_PATTERN` in `congress_gov.py`. Resolution-type bills (`hres`/`sres`/etc.) dropped as symbolic. Reuses the same keyword categorizer — categories are jurisdiction-agnostic. Federal residue is mostly foreign-policy and acronym-only titles (SPUR/SERV/etc.) where the title carries no topical signal. No caching — meant to run on cron, not ad hoc.
- Both: `scheduled_date = status_date + DEFAULT_VOTE_LEAD_DAYS` (14d). Stalled bills with past projected dates get bumped to today so V doesn't go to zero.
- **Stale-row purge** at end of each ingest: deletes `scheduled_votes` rows (and their downstream `alerts`) whose `bill_number` isn't in the current categorized set. Gated on `keepers` being non-empty so a quota error can't nuke the table. Federal ingest *replaces* `seed.py` — re-seeding after an ingest will get re-purged on the next run.

**Pipeline runs federal and state independently.** `pipeline.py` calls `_run_for_jurisdiction` once per actor_type so a federal rep's donations never pair with state bills. Baselines computed in one pass with `GROUP BY actor_type`.

**Stale alert sweep.** After scoring, `_sweep_stale_alerts` deletes any non-dismissed alert whose `(donation_id, vote_id)` pair wasn't refreshed this run. Covers donation aged out, vote already happened, or score recalibrated below threshold. **Dismissed alerts are kept** so user-suppressed history doesn't resurface. Per-`actor_type` scope.

**State alert calibration.** Without it, every state alert lands above urgent because (1) FTM donations are lifetime-stamped today so R saturates to 1.0; (2) state donation pools are too sparse to clear `BASELINE_MIN_SAMPLES=3`, so A defaults to 0.5. Pipeline passes state-only `proxy_donation_r=0.4` (career-flat) and `no_baseline_a=0.0` (honest "no signal") into `score_alert`. Federal is unchanged. Env-overridable: `ALERTS_PROXY_DONATION_R`, `ALERTS_NO_BASELINE_A_HONEST`.

**Auth is local-only — bcrypt + opaque session tokens.** `/api/auth/{signup,login,logout,me}`; 32-byte tokens, 30-day TTL in `sessions` table, `Authorization: Bearer` from frontend. `users` holds `email`, `password_hash`, `name`, `state`, `issues` (JSON list); profile updates via `PATCH /me`. Schema lazy-init via `_ensure_schema()`. Hardening: per-IP/email throttle (8 fails / 15min, 429), constant-time login (bcrypt vs `_DUMMY_PASSWORD_HASH` for unknown emails), `DELETE /me` requires re-auth password, signup rejects ~30 trivial passwords, opportunistic session prune. Missing: email verification, password reset (need SMTP infrastructure).

## Conventions

- Backend: `async`/`await` everywhere, `httpx.AsyncClient`, exponential backoff on 429s.
- New external APIs go in `backend/api/` as their own module, composed in `server.py`.
- Frontend stays single-file. Don't add React Router.

## Deploy / PWA

**Frontend:** Vercel + PWA. `manifest.webmanifest` + `sw.js` + `<link rel="manifest">` make it installable on Android Chrome and iOS Safari "Add to Home Screen." SW registers only when `hostname !== "localhost"` (dev iteration isn't fighting stale caches); pre-caches app shell, network-first otherwise, **`/api/*` deliberately bypassed** so live data never caches. `vercel.json` pins SPA rewrites + `Cache-Control: no-cache` on `/sw.js`.

**PWA-mode UI is a different render path.** Module-level `_IS_PWA_AT_BOOT` snapshot of `display-mode: standalone` + iOS legacy `navigator.standalone`. `App` branches on it: PWA mode returns `renderScreen()` directly with **no dev chrome** (no "Live Prototype" title, screen pills, or phone-frame container). `s.phone` branches at module load: browser is 393×852 framed; PWA is `100% / 100%`. `StatusBar` and Settings "Backend Status" return null in PWA. Don't use a runtime hook — display-mode doesn't change at runtime and `s` needs to branch synchronously.

**Three iOS PWA gotchas in `index.html` standalone CSS** (gated by `@media (display-mode: standalone)`):
1. **Body-lock** to kill rubber-band: `html, body { height: 100%; overflow: hidden; overscroll-behavior: none }` + `body { position: fixed; inset: 0 }`. Scroll happens inside `#root { overflow-y: auto; -webkit-overflow-scrolling: touch; overscroll-behavior: contain }`.
2. **`s.phone` must be `100%`, not `100vw/100vh`** — body has `padding: env(safe-area-inset-*)` already shrinking to safe area; vw/vh reach back into dynamic-island/home-indicator zones and squish proportions.
3. **`status-bar-style: default` does NOT reserve space** on modern iOS — page extends behind the status bar. `padding-top: env(safe-area-inset-top)` is still required. Body bg in PWA mode is `#fdfbf7` (matches `colors.bg`) so safe-area regions read continuous instead of black bands.

**Backend deploy:** `Procfile` works on Railway/Render/Heroku/Fly. Required for full features: `DATA_GOV_API_KEY`, `OPENAI_API_KEY`, `NEWSAPI_KEY`, `GUARDIAN_API_KEY`, `LEGISCAN_API_KEY`, `FTM_API_KEY`. Frontend needs `VITE_API_BASE=https://your-backend-url` in Vercel env before deploying. CORS is `allow_origins=["*"]` — fine for read-only, tighten if surface changes.

- **Persistence caveat:** SQLite alerts DB lives at `backend/data/whoboughtmyrep.sqlite`. Ephemeral filesystems (Vercel functions, Render free tier) lose data on redeploy — use Railway/Fly volumes/Render paid disk.
- **Cron caveat:** Railway/Render have native scheduled jobs; Fly uses scheduled machines. `refresh.py` is the entrypoint.

## Gotchas

- `python -m backend.alerts.*` must run from **project root**, not inside `backend/`. Imports rely on it.
- `/api/alerts/*` 503s until `python -m backend.db` runs and the pipeline has populated.
- Vite proxies `/api/*` → `:8000`. Don't prefix `http://localhost:8000` in frontend fetches.
- For prod frontend builds, `VITE_API_BASE=https://backend-url` before `npm run build`.
- OpenFEC `candidate → principal committee` is fuzzy — see `get_principal_committee` fallback chain in `ingest_fec.py` (scoped cycle, then unscoped, then committee lookup by candidate_id).
- State alerts need cached Legiscan rosters to attribute donations. After a cache wipe: hit the state-rep screen or run `ingest_state_votes` to repopulate before `pipeline.py`.

## Status

Everything wired and live: auth, dashboard, federal+state search, profile/funding/votes, timeline, take-action, contact, settings, alerts (federal + state with calibration), events with news + AI summaries, AI stances + promises (federal + state via Ballotpedia).

Test suite: 34 tests across `test_smoke.py` (HTTP shape, auth, alerts), `test_pipeline.py` (federal/state scoring + stale-sweep + state-calibration anchor at 0.554), `test_classifier.py` (PAC classifier word-boundary + transport-vs-union regressions).

**Deferred:** FTM live `_live_find_eid` — candidate enumeration by state is blocked on undocumented FTM filter syntax. Workaround is `backend/data/ftm_eids.csv` (manual append after looking up on followthemoney.org). Email verification + password reset need SMTP infrastructure.
