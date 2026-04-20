# Fudge Ur Uncle

Politician accountability app. Follow the money. Track votes. Take action.

## What's Inside

```
fudge-ur-uncle-full/
├── backend/      # Python FastAPI server (campaign finance, votes, reps)
└── frontend/     # React + Vite app (17 screens, wired to backend)
```

## Run It (2 terminals)

### Terminal 1 — Backend
```bash
cd backend
pip install -r requirements.txt
python server.py
# Server runs at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Terminal 2 — Frontend
```bash
cd frontend
npm install
npm run dev
# App runs at http://localhost:5173
```

Open http://localhost:5173 in your browser and you should see the app connected to the backend.

## API Keys (optional — works without them using sample data)

Sign up free at [api.data.gov/signup](https://api.data.gov/signup/) and [whoboughtmyrep.com/developers](https://whoboughtmyrep.com/developers), then:

```bash
export DATA_GOV_API_KEY=your_key
export WHOBOUGHTMYREP_API_KEY=your_key
cd backend && python server.py
```

See `backend/README.md` and `frontend/README.md` for more details.
