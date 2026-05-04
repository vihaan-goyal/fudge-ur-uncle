# Fudge Ur Uncle — Frontend

React + Vite frontend that connects to the Fudge Ur Uncle backend API.

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Start the backend first (in a separate terminal)
cd ../backend
python server.py

# 3. Start the frontend
npm run dev

# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
```

Vite's dev server proxies `/api/*` requests to `http://localhost:8000`, so you don't need CORS config.

## What's Wired to the Backend

| Screen | Endpoint | Status |
|--------|----------|--------|
| Auth (signup/login/logout/settings) | `POST/GET/PATCH/DELETE /api/auth/*` | Live |
| Dashboard | `GET /api/reps/by-state/{state}` + per-rep `/funding-lite` | Live (lazy-loaded funding) |
| Unified Search | `GET /api/search/unified?q={q}&state={st}` | Live (federal + state) |
| Politician Profile | `GET /api/profile/{bioguide_id}` | Live |
| Funding | Uses profile data | Live |
| Voting History | Uses profile data | Live |
| Timeline | Uses profile data | Live |
| Stance Analysis | `GET /api/profile/{bioguide_id}/stances` | Live (requires `OPENAI_API_KEY`) |
| Promise Scoring | `GET /api/profile/{bioguide_id}/promises` | Live (requires `OPENAI_API_KEY`) |
| Take Action | Uses profile contact data | Live |
| Contact Reps | `GET /api/reps/by-state/{state}` | Live |
| Events | `GET /api/events` + `/article` + `/summary` | Live (Congress.gov + NewsAPI/Guardian + OpenAI) |
| Alerts | `GET /api/alerts/by-actor/{actor_type}/{actor_id}` | Live (when pipeline has run) |
| State Legislators | `GET /api/state-reps/by-state/{state}` | Live (Legiscan, with sample fallback) |
| State Rep Profile | `GET /api/state-reps/{people_id}` (+ `/votes`, `/stances`, `/promises`) | Live |
| Settings | `PATCH /api/auth/me` | Live |

## Graceful Fallback

Every API call wraps in `useApi()`, which falls back to embedded sample data if the backend is unreachable. An "OFFLINE" badge appears in the status bar so you know you're looking at sample data.

## Production Build

```bash
npm run build
# Static files output to ./dist
```

Set `VITE_API_BASE` to your deployed backend URL:
```bash
VITE_API_BASE=https://api.your-domain.com npm run build
```

## Project Structure

```
fudge-ur-uncle-frontend/
├── package.json
├── vite.config.js       # Proxy /api → localhost:8000
├── index.html
├── .env.example
└── src/
    ├── main.jsx         # Entry point
    ├── api.js           # API client + sample fallback data
    └── App.jsx          # All 23 screens + routing (single file, intentional)
```
