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
│   │   ├── promises.py           # scrapes rep's .gov site, GPT scores stated promises vs votes
│   │   ├── ai_cache.py           # persistent SQLite cache for promises + stances + Legiscan (TTL 7d)
│   │   ├── legiscan.py           # Legiscan API wrapper - state legislators, sponsored bills, roll calls
│   │   ├── state_sites.py        # derives a Ballotpedia URL for state legislators (for promise scraping)
│   │   ├── followthemoney.py     # FollowTheMoney/NIMP API - state campaign-finance aggregates
│   │   ├── auth.py               # /api/auth/* - signup/login/me/logout, bcrypt + opaque tokens
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
│       ├── ingest_ftm.py         # pulls FollowTheMoney aggregates into DB (state side)
│       ├── ingest_state_votes.py # pulls Legiscan engrossed bills into scheduled_votes
│       ├── state_categories.py   # bill title -> alert category (keyword regex)
│       ├── catcode_map.py        # OpenSecrets/CRP Catcode -> our industry name
│       └── seed.py               # seed data for dev
└── frontend/          # React + Vite app
    ├── package.json
    ├── vite.config.js            # proxies /api -> localhost:8000
    └── src/
        ├── main.jsx              # entry
        ├── api.js                # fetch wrapper + endpoint methods
        └── App.jsx               # all 23 screens + routing (single file)
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
- `LEGISCAN_API_KEY` - legiscan.com. Powers `/api/state-reps/*`. Free tier is 30k req/month + 1 req/sec; results are cached in `ai_cache` (7d for rosters, 24h for profiles) to stay well under the limit.
- `FTM_API_KEY` - followthemoney.org (NIMP). Powers state-side `ingest_ftm.py`. Free tier; aggregates are cached in `ai_cache` (24h for industry breakdowns, 7d for eid lookups). Without a key, the ingester falls back to a small CT sample dict so the pipeline can be exercised end-to-end.

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

**Promise scoring scrapes the rep's official site, then grades vs. votes.** `GET /api/profile/{bioguide_id}/promises` runs a two-phase pipeline in `backend/api/promises.py`: (1) fetch the homepage and common issue paths (`/issues`, `/priorities`, `/about`, etc.) in parallel with `asyncio.gather`, regex-strip HTML to plain text, cap at 14k chars; (2) send that text plus the legislator's substantive votes and sponsored bills to GPT-4o-mini, which extracts 4–6 stated positions and labels each KEPT / BROKEN / PARTIAL / UNCLEAR with strict evidence rules (direct subject match only, no hedge words). Requires `OPENAI_API_KEY`; returns `{"promises": null, "scraped": false}` if the key is missing or scraping yielded <400 chars (common when sites are JS-rendered). Cached in-process per bioguide_id. Substantive-vote filtering is shared with stance_analysis via `is_substantive_vote()` / `format_vote_lines()` / `format_bill_lines()` in `backend/api/congress_gov.py`.

**State legislators come from Legiscan.** `GET /api/state-reps/by-state/{state}` returns the current-session roster (chamber, district, party, `people_id`). `GET /api/state-reps/{people_id}` returns the profile plus up to 15 most recent sponsored bills. `backend/api/legiscan.py` does a two-step fetch (`getSessionList` → newest session → `getSessionPeople`) for rosters, and `getPerson` + `getSponsoredList` for profiles. All results go through `ai_cache` (7d for rosters, 24h for profiles, 24h for votes) because the free tier caps at 30k req/month. Falls back to `SAMPLE_STATE_LEGISLATORS` (CT only) if the key is missing or the upstream fails. **Legiscan gotcha:** `getSponsoredList` returns `bills` as a flat list at `sponsoredbills.bills` with a `session_id` on each item; `sponsoredbills.sessions` is just session metadata, *not* nested bills. Sort by `session_id` desc to get newest-first.

**State-rep deep-dive endpoints mirror the federal flow.** `GET /api/state-reps/{people_id}/votes` returns recent roll-call votes by fetching bill detail for the rep's most recent sponsored bills (capped at 8) and pulling the latest roll call from each (`getBill` → `getRollCall`). `GET /api/state-reps/{people_id}/stances` reuses `stance_analysis.py` with a `stances:state:{people_id}` cache key. `GET /api/state-reps/{people_id}/promises` reuses `promises.py` with a `promises:state:{people_id}` cache key, where the website URL is derived by `state_sites.derive_website()` (defaults to Ballotpedia URL pattern, with per-state overrides possible). Note: the votes endpoint only finds rolls on bills the rep *sponsored*; backbench reps with sparse sponsorship will see thin results.

**Search is unified across federal + state.** `GET /api/search/unified?q=...&state=CT` fans out to `legislators.search_by_name` (federal, GitHub data) and `legiscan.search_state_legislators` (state, filtered against the cached roster) in parallel via `asyncio.gather`. Each result is tagged with `level: "federal" | "state"` so the frontend `SearchScreen` can route clicks to the correct profile screen (federal → `bioguide_id`, state → `people_id`). `state` param is optional; when omitted only federal results are returned.

**AI results are cached in SQLite, not just in-process.** Promise scoring and stance analysis both go through `backend/api/ai_cache.py`, which stores results in an `ai_cache` table (`cache_key`, `value_json`, `expires_at`) with a default 7-day TTL. Keys are namespaced: `promises:{bioguide_id}`, `stances:{bioguide_id}`, `promises:state:{people_id}`, `stances:state:{people_id}`, `legiscan:people:{state}`, `legiscan:profile:{people_id}`, `legiscan:votes:{people_id}`. The table is created lazily on first access, so the cache works even if `python -m backend.db` hasn't been run. A server restart no longer discards results, and repeat visits don't re-hit OpenAI. Rationale: each call is 30-90s and costs money. **Cache-bust gotcha:** if a parser bug poisons cached entries with empty data, the bad results stick for the TTL — wipe the relevant rows from `ai_cache` directly when fixing parsers.

**Alert scoring is a documented formula, not a heuristic.** `backend/alerts/scoring.py` computes `S = (T*V) * (alpha*D + beta*R + gamma*A) * (1 + delta*N)` where T=topic match, V=vote proximity, D=donation magnitude, R=recency, A=anomaly z-score, N=news salience. Topic match uses the table in `industry_map.py`. Thresholds: S>0.3 → alert, S>0.6 → urgent. All intermediate signals are stored on the alert for explainability.

**Alerts schema is polymorphic across federal and state actors.** `donations`, `alerts`, and `industry_baselines` all key on `(actor_type, actor_id)` instead of `bioguide_id` — `actor_type` is `'federal'` (with `actor_id` = bioguide ID) or `'state'` (with `actor_id` = Legiscan `people_id`). `scheduled_votes` similarly carries `(jurisdiction, state_code)` with `UNIQUE (jurisdiction, state_code, bill_number)` so a CT bill and an NJ bill with the same number don't collide. Legacy DBs are migrated in place by `db._migrate()`: simple column changes use `ALTER TABLE RENAME COLUMN` + `ADD COLUMN`; the PK / UNIQUE-constraint changes on `industry_baselines` and `scheduled_votes` use the SQLite table-swap idiom with FK enforcement temporarily off. Migration runs *before* `executescript(SCHEMA)` because the new schema's indexes reference columns that don't exist on legacy tables yet. The `/api/alerts` endpoint accepts both the new `actor_type`/`actor_id` query params and the legacy `bioguide_id` (which auto-maps to `actor_type=federal`); response objects include both for backward compatibility, with `bioguide_id` populated only when `actor_type='federal'`.

**External IDs are stored in a separate join table, not on actor rows.** `external_ids(actor_type, actor_id, source, external_id, confidence, matched_at)` maps an actor (federal bioguide ID or state Legiscan people_id) to its identifier in third-party datasets (FTM eid, OpenSecrets candidate ID, FEC candidate ID, etc.). Primary key is `(actor_type, actor_id, source)`; reverse-lookup index on `(source, external_id)`. This keeps the polymorphic `donations`/`alerts` schema free of per-source columns and means adding a new data source (OpenStates, OpenSecrets, etc.) doesn't require schema churn. Confidence captures fuzzy-match quality so downstream code can decide how much to trust an attribution.

**State donations come from FollowTheMoney aggregates, not itemized rows.** `backend/api/followthemoney.py` is the FTM/NIMP client; `backend/alerts/ingest_ftm.py` is the orchestrator. Pipeline per state legislator: pull the cached Legiscan roster → resolve each rep's FTM eid via fuzzy name match (`SequenceMatcher` ratio ≥ 0.78, stored in `external_ids` for reuse) → fetch lifetime industry breakdown via `dataset=contributions&gro=d-cci&c-t-eid=<EID>` → translate FTM `General_Industry` string → our industry via `catcode_map.industry_for_ftm_name` (drops `_ignore` buckets like "Candidate Contributions"/"Uncoded"/"Public Subsidy"/"Retired") → write a `donations` row tagged `actor_type='state'` for each kept industry bucket. Each FTM bucket becomes one donation row with `pac_name` = "{General_Industry} (FTM lifetime aggregate, N records)" and `donation_date` = today (FTM grouped-aggregates are lifetime-only — `y=`/`f-y=` filters return 0 records when combined with grouping, so per-cycle breakdown isn't available; today keeps rows inside the 180-day lookback). Dedup uses `fec_filing_id = "FTM:{eid}:lifetime:{industry_slug}"`. Connection lifetime is per-actor — holding `with connect()` across the loop's `await`s starves `ai_cache` writes and triggers SQLite "database is locked" errors. Committee pseudo-entries from the Legiscan roster (rows like "Judiciary Committee" with empty chamber) are filtered out before any FTM lookup. The ingester falls back to `SAMPLE_FTM_EIDS` + `SAMPLE_FTM_AGGREGATES` (CT-only, two reps; sample data is keyed by FTM industry name to match live shape) when `FTM_API_KEY` is missing or returns errors. **EID lookup is currently a stub** — `_live_find_eid` returns None because the candidates dataset's state-filter syntax is undocumented (none of `s-y-st`, `s`, `c-r-s`, `c-t-s`, `c-r-osj` honor a state filter empirically). With a real key, the ingester therefore still falls through to sample-eid matches. Fix is probably to download FTM's static entity directory and do name matching client-side. **Cache pollution gotcha:** test runs that misconfigure `db.DB_PATH` will write `[]` (no-match) sentinels to the production `ai_cache` table; if FTM matches mysteriously stop returning, wipe rows where `cache_key LIKE 'ftm:%'`. **Free-tier quota gotcha:** FTM's free tier returns HTTP 200 with `{"error": "This account has reached its free API call limit pending Institute review..."}` when exhausted (not a 4xx). `_ftm_get` detects this and returns `{}`; the wrapper then falls back to sample data.

**State "upcoming vote" feed uses bill-status as a proxy.** State legislatures don't publish a clean scheduled-vote calendar, so `backend/alerts/ingest_state_votes.py` reads the Legiscan masterlist for the current session, filters to `STATUS_ENGROSSED` (passed one chamber, headed to the other — the most reliable "imminent floor vote" signal), and writes those bills to `scheduled_votes` tagged `jurisdiction='state'`. Bill titles are mapped to alert categories by keyword regex in `backend/alerts/state_categories.py` — 13 categories total: `environment`, `healthcare`, `economy`, `defense`, `infrastructure`, `technology`, `labor`, `agriculture`, `housing`, `education`, `immigration`, `firearms`, `elections` (no per-bill Legiscan call — `getBill` would burn the 30k/month free tier on a masterlist with hundreds of bills). **Categorization is title-only** — the description-fallback path was removed because Legiscan's `description` is a long policy summary that produces too many incidental matches (a building-code bill got tagged `education` because its description happened to mention schools). Bills whose title matches no category are silently dropped at ingest. On a typical CT masterlist (210 engrossed bills, May 2026), ~69% remain uncategorized — these are largely procedural (land conveyances, claims commissioner resolutions, judicial branch operations) and are unlikely to ever produce useful donation/vote correlations. **Stale-row purge:** at the end of each ingest the script also deletes `scheduled_votes` rows (and their downstream `alerts`) whose `bill_number` is no longer in the current categorized set — bills that fell off the masterlist (passed/failed) or were re-categorized to None won't linger generating phantom alerts. Date semantics differ from federal: federal `scheduled_date` is the real upcoming floor-vote date, state `scheduled_date` is `status_date + DEFAULT_VOTE_LEAD_DAYS` (14 days by default, the typical engrossment-to-receiving-chamber-vote interval). Stale bills whose projected date is already past get bumped to `today` so V doesn't go to zero — engrossed bills are still pending business until they pass or fail. The masterlist is cached in `ai_cache` for 6 hours.

**The alert pipeline runs federal and state independently.** `pipeline.py` calls `_run_for_jurisdiction` once with `actor_type='federal', jurisdiction='federal'` and once with `actor_type='state', jurisdiction='state'` so a federal rep's donations never get paired with state bills (and vice versa). Baselines are still computed in one pass — `recompute_baselines` GROUPs BY `actor_type` so federal and state baselines stay separate. **State alert volume is much higher than expected:** in a real run against live Legiscan data (CT, May 2026, 8 sample-eid donations + 66 ingested bills), the pipeline produced 98 state alerts of which 33 were urgent (score > 0.6). Two reasons inflate state scores: (1) the `status_date + lead_days` date proxy gets clamped to `today` for stale-engrossed bills, so V≈1.0 across the board, and (2) the state baseline pool is tiny (8 donations across 5 industries), so anomaly A defaults to its 0.5 fallback. Both are by-design pragmatics, not bugs — but be aware that a state-rep profile's Alerts tab will look much louder than the federal equivalent until the state donation pool grows past `baseline_min_samples=3` per industry.

**FTM aggregates are lifetime — donation_date is always today.** FTM's grouped-aggregate endpoint doesn't honor year filters, so we can't break out donations per cycle. `ingest_ftm.py` writes one row per industry per legislator (lifetime total) with `donation_date = today` so the row stays inside the pipeline's 180-day lookback. This overstates recency relative to itemized FEC data, but per-cycle FTM data isn't available at the free-tier aggregate endpoint — the alternative would be pulling itemized rows, which would burn the monthly quota fast.

**Auth is local-only — bcrypt + opaque session tokens, no third-party identity provider.** `backend/api/auth.py` exposes `/api/auth/{signup,login,logout,me}` (GET/PATCH/DELETE on `/me`). Passwords are bcrypt-hashed; session tokens are 32-byte `secrets.token_urlsafe` strings with a 30-day TTL, stored in the `sessions` table and validated by the `get_current_user` dependency on each request. The frontend stores the token in `localStorage` (`fuu_token`) plus a cached user object (`fuu_user`); `frontend/src/api.js` auto-attaches `Authorization: Bearer <token>` to every request. The `users` table holds `email`, `password_hash`, `name`, `state`, and `issues` (JSON-encoded list); profile updates from the Settings screen and the issue-select screen go through `PATCH /api/auth/me`. Schema is lazy-initialized via `_ensure_schema()` (gated by a module-level `_schema_ready` flag, like `ai_cache.py`), so the first auth request creates the tables; existing DBs pick up new columns through `db._migrate()`. There's no email verification, password reset, or rate limiting — this is a hackathon-grade auth, not production.

## Conventions

- Backend: `async`/`await` everywhere, `httpx.AsyncClient` for outbound calls, retry with exponential backoff on 429s.
- All endpoints return JSON with consistent shapes. Add new ones to `server.py` next to similar existing endpoints.
- New external APIs go in `backend/api/` as their own module, then composed in `server.py`.
- Frontend is intentionally a single `App.jsx` file - all 23 screens, styles via inline `style={s.foo}` objects against a shared `s` style map. Don't split this up casually; the single-file structure was a deliberate choice.
- Frontend screens are switched via a `currentScreen` state + `SCREENS` enum, not React Router.

## Gotchas

- `python -m backend.alerts.pipeline` must run from the **project root**, not from inside `backend/`. The package imports rely on it.
- `backend/data/whoboughtmyrep.sqlite` is created on first run of `python -m backend.db`. The `/api/alerts/*` endpoints will 503 until that and the pipeline have run.
- Vite proxies `/api/*` to `localhost:8000`, so don't add `http://localhost:8000` prefixes in frontend fetches - just use `/api/...`.
- For production frontend builds, set `VITE_API_BASE=https://your-backend.example.com` before `npm run build`.
- The OpenFEC `candidate -> principal committee` resolution is fuzzy. See `get_principal_committee` in `ingest_fec.py` for the fallback chain (try scoped cycle, then unscoped, then committee lookup by candidate_id).

## Status (May 2026)

Wired and live: local auth (signup/login/logout, bcrypt + bearer-token sessions, persisted state + issue preferences via `PATCH /api/auth/me`), dashboard, unified federal+state search, profile, funding, voting history, timeline, take-action, contact reps, settings, alerts (when pipeline has run), events + event detail (real Congress.gov committee meetings, NewsAPI news articles, OpenAI plain-English summaries), AI stance analysis on profile screen, AI promise scoring on profile screen (scrapes rep's .gov site, scores stated promises vs votes — both AI features require `OPENAI_API_KEY`), state legislators screen (Legiscan roster, sample-data fallback when `LEGISCAN_API_KEY` is missing), state-legislator profile deep-dive (votes, stances, promises — same AI pipeline as federal, with Ballotpedia as the scrape target).

State alerts pipeline is now producing real cards on the UI (verified end-to-end May 2026 against live Legiscan + sample-eid FTM donations). Flow: polymorphic schema (`actor_type`/`actor_id`, `external_ids`) → `ingest_ftm.py` writes FTM-aggregate donations tagged `actor_type='state'` (currently 8 rows for Looney + Ritter via `SAMPLE_FTM_EIDS` — eid lookup for arbitrary state legislators is still a stub) → `ingest_state_votes.py` reads the live Legiscan masterlist (210 engrossed CT bills on a typical run) and writes 66 categorized bills to `scheduled_votes` tagged `jurisdiction='state'` → `pipeline.py` runs federal and state independently → `StateRepAlertsScreen` (Alerts tab on the state-rep profile) calls `GET /api/alerts/by-actor/state/{people_id}` and renders cards with score/urgent/donation→vote pairing/T,V,D,R signals. **Last verified run (post title-only categorization + stale-row purge, May 2026):** Looney `5631` got 72 alerts (26 urgent, top 0.86: Public Sector Unions × education); Ritter `10807` got 26 alerts (7 urgent, top 0.82: Pharmaceuticals × healthcare). State alerts break down across 7 categories led by healthcare (45), education (17), environment (16), and economy (16).

Deferred / not yet implemented:
- **FTM eid lookup.** Live aggregate-fetching is verified working (`dataset=contributions&gro=d-cci&c-t-eid=<EID>` returns the right shape on real keys), but candidate enumeration by state is blocked on FTM's undocumented state-filter syntax — `_live_find_eid` is a stub. With a real `FTM_API_KEY`, ingest still falls through to `SAMPLE_FTM_EIDS` (Looney + Ritter only). Likely fix: pull FTM's entity directory dump and match names client-side. Until then, only the two sample reps will have donor data on their alert cards. **Current dev key is quota-exhausted ("pending Institute review")** — empirical probing of new filter prefixes is not possible until the cap resets or a new key is registered, so an offline bulk-download strategy is the more realistic path forward.