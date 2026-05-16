# Fudge Ur Uncle

Politician accountability app. Tracks federal + state legislators, follows campaign donations, correlates with upcoming votes, surfaces alerts. Mobile-first React/FastAPI, deployed as Vercel PWA + Procfile backend.

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
    auth.py alerts_router.py upcoming_votes_router.py
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
    App.jsx          # all 24 screens + routing in one file (deliberate)
    groupAlerts.js   # client-side alert grouping (extracted for unit tests)
    copy.js          # centralized user-facing strings (tone swap-point)
```

## Run Commands

From project root (imports require it):

```
cd backend && pip install -r requirements.txt && python server.py     # :8000
cd frontend && npm install && npm run dev                              # :5173
python -m backend.db                       # init schema, first run only
python -m backend.alerts.refresh           # cron: federal+state ingest then pipeline
cd backend && python -m pytest tests/ -v
cd frontend && npm test
```

`refresh` flags: `--states CT`, `--skip-federal`, `--skip-state`, `--congress 119`. Ingester failures log but don't block. Don't mix `seed.py` and `refresh` against the same DB — refresh purges seed rows on each run.

## Environment

`backend/.env` (all optional — missing keys fall back to sample data or DEMO_KEY):

- `DATA_GOV_API_KEY` — Congress.gov + OpenFEC
- `OPENAI_API_KEY` — gpt-4o-mini for stances, promises, event summaries, AI categorization
- `NEWSAPI_KEY` — primary news source (100 req/day free)
- `GUARDIAN_API_KEY` — fallback news source
- `WHOBOUGHTMYREP_API_KEY` — industry-attributed funding
- `LEGISCAN_API_KEY` — state legislators (30k/mo + 1 req/sec, cached)
- `FTM_API_KEY` — FollowTheMoney state campaign finance

`GET /` reports all 7 keys — keep in sync when adding env-dependent features.

## Architecture

**Backend is a thin aggregator.** External APIs in `backend/api/*.py`; `server.py` composes them. Only alerts persist to SQLite — everything else is live with in-process caching.

**Frontend has graceful fallback.** Every screen catches API errors and falls back to sample data with an "OFFLINE" badge. Don't remove — it's the demo path. `apiRequest` auto-clears localStorage on 401 (only when a token was sent).

**Single-file frontend.** `App.jsx` holds all 24 screens. Inline `style={s.foo}` on a shared `s` map. Routing via `currentScreen` + `SCREENS` enum, not React Router. Don't split. Exceptions: `groupAlerts.js` (testable isolation) and `copy.js` (user-facing strings — single tone swap-point). New user-visible strings on any covered screen go through `COPY`. Inline placeholders and one-off validation errors stay hardcoded in `App.jsx`.

**Typography rule:** `s.headerTitle`/`s.sectionTitle`/`s.btn`/`s.input`/`s.chip`/`s.badge`/`s.navItem`/`s.backBtn` use `fontSans` (IBM Plex Sans). `fontFamily: font` (IBM Plex Mono) is reserved for data: dollar amounts, vote dates, bill IDs, score numbers, chamber badges, `<code>`, avatar/party glyphs, dev chrome. Don't reintroduce mono on form labels, subtitles, error messages, empty states, or attribution notes.

**Category display:** always use `friendlyCategory()` / `friendlyCategoryInline()` from `copy.js` — never raw keys or `charAt(0).toUpperCase()`.

**Civics glossary:** `GLOSSARY` in `copy.js` (term key → `{label, body}`). Wrap user-visible jargon with `<TermTip term="pac">PAC</TermTip>` — dotted underline + tap-to-define popover. Popover portals to `document.body` with `position: fixed` because rep cards use `transform` (would otherwise convert nested `position: fixed` into card-relative `absolute`). Scrim stops `click`/`pointerdown`/`mousedown`/`touchstart` so the underlying button doesn't fire on dismiss.

**Dashboard** targets new voters / immigrants: quick actions → Coming up → Your reps. "Coming up" calls `/api/upcoming-votes`, renders first 3. Personalized by user issues when signed in.

**Warm-card surfaces** (`ComingUpCard`, `RepCardShell`, `QuickActionButton`) bypass `s.card` — white surface, accent-tinted shadow. `ComingUpCard` outer is a non-interactive `<div>`; each row is its own `<button>` (global CSS press feedback, no JS state). Don't mix warm-card and cream `s.card` on the same surface.

**Motion:** `fuu-anim-styles` (module-level `<style>`, idempotent on HMR) defines `fuu-fade-up`, `fuu-shimmer`, `fuu-soft-pulse` + global `button:active` press rule + `prefers-reduced-motion` blanket. Staggered lists use `<FadeIn delay={Math.min(i*N, cap)}>`. Don't add JS-driven perpetual animation — use CSS keyframes.

**`users.issues`** stores the 14 backend category keys (lowercase, e.g. `healthcare`, `foreign_policy`) — same set `scheduled_votes.category` uses. Fresh signups start `[]`; Done button disabled until ≥1 chip picked.

**`/api/upcoming-votes`:** `state` (federal always included), `categories` (comma-separated, validated, 400 on unknown), `limit` (≤100). Auth-optional: signed-in user's issues used as default categories; explicit param overrides. Response includes `personalized` flag.

**Alerts grouped client-side** by `(actor_id, industry, category)` in `groupAlerts.js`. `{category}` slot uses `friendlyCategoryInline()` — don't inline the raw key.

**Profile endpoint** `/api/profile/{bioguide_id}`: bio + funding + votes, cached 6h. Dashboard lazy-loads `/api/reps/{id}/funding-lite` (24h hits, 15min `has_data:False` sentinel — self-heals transient WBMR/FEC misses).
- **Thin-WBMR guard:** don't write cache when `top_industries==[]` and `total_raised>$100K` — WBMR occasionally serves stripped records.
- **FEC ID:** probe all `fec_ids[]` in parallel, pick first with non-empty `total_receipts` — prior House IDs return empty totals under current-cycle filter.
- **Principal committee:** query `/candidate/{id}/committees/?designation=P` — FEC removed `principal_committees` from candidate payload.
- **Employer noise:** skip `RETIRED/SELF/HOMEMAKER/UNEMPLOYED/NOT EMPLOYED/NONE/N/A/INFORMATION REQUESTED`.

**Events:** `/api/events` fetches Congress.gov meeting stubs then gathers ≤10 detail URLs. 5-min in-process cache. Detail lazily fetches news + AI summary (gpt-4o-mini, 2 sentences). Past meetings dropped; unparseable dates kept.

**AI stances + promises** require `OPENAI_API_KEY`. Stances: 4–6 policy areas, CONSISTENT/INCONSISTENT/MIXED/PENDING. Promises: scrape rep site → GPT labels KEPT/BROKEN/PARTIAL/UNCLEAR. Promise fallback ladder: (1) primary site, (2) JSON-LD/noscript, (3) Wikipedia, (4) Ballotpedia. Stops at first rung ≥400 chars. No Playwright.

**Mamu (AI civics helper):** `POST /api/assistant/chat` (auth-required), gpt-4o-mini. Dedicated bottom-nav tab + floating pill that navigates to tab. Chat state lifted to App. `lastNonAssistantScreen` tracker resolves context when on the tab. Context: federal profile cluster → `{rep_id, rep_name}`, state cluster → `{state_rep_id}`, event → `{event_title}`. Reads cache only — no live upstream. Capped 30 turns. Responses cached 24h. Rename via `COPY.assistant` in `copy.js`.

**Unified search:** `/api/search/unified?q=...&state=CT` fans out federal + state in parallel; tagged `level: "federal"|"state"`.

**State legislators from Legiscan.** Rate-limited: 1.05s lock per call (don't remove without paid-tier flag). Chamber: always "House" for lower chamber even in Assembly states. `getSponsoredList` returns flat `sponsoredbills.bills` — sort by `session_id` desc. Vote index `legiscan:vote_index:{state}` (24h) built once per refresh cycle; falls back to sponsored-only on cold cache.

**Cache keys** (`ai_cache.py`, SQLite — bust with `DELETE FROM ai_cache WHERE cache_key LIKE 'profile:%'`):

| Key | TTL |
|-----|-----|
| `profile:{bioguide_id}` | 6h |
| `funding_lite:{bioguide_id}` | 24h (15min on `has_data:False`) |
| `legiscan:people:{state}` | 7d |
| `legiscan:profile:{pid}`, `legiscan:votes:{pid}`, `legiscan:vote_index:{state}`, `legiscan:bill:{id}`, `legiscan:rollcall:{id}` | 24h |
| `cat:{sha1(title+desc)}` | 30d |
| `chat:{user_id}:{sha1(messages+context)}` | 24h |

**Alert scoring:** `S = (T*V) * (αD + βR + γA) * (1 + δN)`. `S>0.3` → alert, `S>0.6` → urgent. All signals stored for explainability.

**Alerts schema polymorphic:** `donations`/`alerts`/`industry_baselines` key on `(actor_type, actor_id)` — `'federal'` (bioguide) or `'state'` (Legiscan people_id). `scheduled_votes` keys on `(jurisdiction, state_code, bill_number)`. Migrations in `db._migrate()` run before schema executescript. `/api/alerts` accepts legacy `bioguide_id` auto-mapped to federal.

**Alerts timestamps:** `updated_at` bumped on re-confirmation. Use `datetime.now(timezone.utc).replace(tzinfo=None)` — SQLite `CURRENT_TIMESTAMP` is UTC-naive.

**State donations from FTM lifetime aggregates.** EID lookup: `backend/data/ftm_eids.csv` (offline, fuzzy match ≥0.78, chamber as disambiguator). To add EIDs: look up on followthemoney.org, run `scripts/find_ftm_eids.py CT House`. NJ quirk: "House" roster mixes Senate — tag `SD-` districts as Senate.
- **Connection:** open per-actor, not across `await`s — causes SQLite "database is locked".
- **Quota:** FTM free tier returns HTTP 200 with error JSON. Returns sample data, does NOT cache.
- **Cache pollution:** test misconfiguration writes `[]` sentinels. Wipe `cache_key LIKE 'ftm:%'` if FTM matches stop.

**Upcoming votes** use bill-status as proxy. State: `STATUS_ENGROSSED`, title-only keyword regex (14 categories), gpt-4o-mini AI fallback on misses (cached 30d). Federal: Congress.gov floor-action pattern, 4×250 pages, resolution types dropped. Both: `scheduled_date = status_date + 14d`. Stale-row purge at end of ingest gated on non-empty keepers.

**Pipeline** runs federal and state independently (`_run_for_jurisdiction` per actor_type). After scoring, `_sweep_stale_alerts` deletes non-dismissed alerts not refreshed this run. Dismissed alerts kept. **State calibration:** `proxy_donation_r=0.4`, `no_baseline_a=0.0` (FTM lifetime stamps saturate R; sparse pools can't clear baseline). Env-overridable: `ALERTS_PROXY_DONATION_R`, `ALERTS_NO_BASELINE_A_HONEST`.

**Auth:** bcrypt + opaque 32-byte tokens, 30-day TTL. `get_current_user_optional` for personalize-but-serve-anon endpoints. Hardened: 8-fail/15min throttle, constant-time login, trivial-password reject. Missing: email verification, password reset (need SMTP).

**Guest mode (temporary):** `handleEnterGuest` sets `currentUser.is_guest=true`, no token written. All auth handlers bypass API. Mamu shows sign-up CTA. Rollback: grep `is_guest`/`isGuest`/`handleEnterGuest`/`onEnterGuest`.

## Conventions

- Backend: `async`/`await`, `httpx.AsyncClient`, exponential backoff on 429s.
- New external APIs: `backend/api/` module, composed in `server.py`.
- Frontend: single-file, no React Router.

## Deploy / PWA

Frontend: Vercel + PWA. SW registers only on non-localhost; `/api/*` bypassed (live data never caches).

**PWA-mode:** `_IS_PWA_AT_BOOT` module-level snapshot (not a hook — display-mode doesn't change at runtime). PWA returns `renderScreen()` directly, no dev chrome. `s.phone` is `100%/100%`.

**iOS PWA gotchas** (in `index.html`, gated by `@media (display-mode: standalone)`):
1. Body-lock: `position: fixed; inset: 0` on body; scroll in `#root { overflow-y: auto; -webkit-overflow-scrolling: touch }`.
2. Use `100%` not `100vw/100vh` — safe-area padding already shrinks body; vw/vh squish into dynamic-island zones.
3. `safe-area-inset-top` padding required even with `status-bar-style: default`.

**Backend deploy:** Procfile (Railway/Render/Heroku/Fly). `VITE_API_BASE` goes on **Vercel**, not backend host — Vite inlines at build time. Symptom of missing: iOS PWA login fails with "Load failed" (SPA rewrite returns HTML instead of JSON). Fix: Vercel env var → redeploy → reinstall PWA.

**Persistence:** SQLite at `backend/data/whoboughtmyrep.sqlite` — use persistent disk (Railway/Fly volumes, not Render free tier).

## Gotchas

- Run `python -m backend.alerts.*` from **project root** — imports require it.
- `/api/alerts/*` 503s until `python -m backend.db` + pipeline run.
- Don't prefix `http://localhost:8000` in frontend fetches (Vite proxies `/api/*`).
- State alerts need cached Legiscan rosters — hit state-rep screen or run `ingest_state_votes` after a cache wipe before `pipeline.py`.

## Status

All features live: auth + guest mode, dashboard, federal+state search, profile/funding/votes/timeline, alerts (federal+state calibrated), events+AI summaries, stances, promises, Mamu chat tab+pill, learn-to-vote.

196 tests across: smoke, pipeline, classifier, state categories, vote index, promise fallbacks, upcoming votes, funding lite.

**Deferred:** FTM live EID lookup (undocumented filter syntax — use CSV). Email verification + password reset (need SMTP).
