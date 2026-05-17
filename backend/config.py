"""
Fudge Ur Uncle - Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the backend folder, regardless of CWD
load_dotenv(Path(__file__).parent / ".env")

# -- API Keys --
# A single api.data.gov key works for BOTH OpenFEC and Congress.gov
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "DEMO_KEY")
WHOBOUGHTMYREP_API_KEY = os.getenv("WHOBOUGHTMYREP_API_KEY", "")
LEGISCAN_API_KEY = os.getenv("LEGISCAN_API_KEY", "")
GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FTM_API_KEY = os.getenv("FTM_API_KEY", "")

# -- Email (Resend) --
# RESEND_API_KEY drives transactional email (verification, password reset).
# When missing, the email_sender module logs the link to stdout instead of
# sending — useful in dev and on hosts where outbound SMTP is blocked.
# RESEND_FROM must be a verified sender on the Resend dashboard.
# FRONTEND_URL is the absolute origin used to build user-facing verify/reset
# links (the emails point at the SPA, which extracts the token from ?verify=
# or ?reset= and POSTs to the API).
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Fudge Ur Uncle <onboarding@resend.dev>")
# Webhook signing secret from the Resend dashboard (Webhooks → reveal). When
# unset, the /api/webhooks/resend handler rejects every request as a safety
# default — we don't want to flip notify_alerts off based on unverified input.
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# -- Base URLs --
GUARDIAN_BASE = "https://content.guardianapis.com"
NEWSAPI_BASE = "https://newsapi.org/v2"
OPENFEC_BASE = "https://api.open.fec.gov/v1"
CONGRESS_GOV_BASE = "https://api.congress.gov/v3"
WHOBOUGHTMYREP_BASE = "https://whoboughtmyrep.com/api/v1"
LEGISCAN_BASE = "https://api.legiscan.com"
LEGISLATORS_GITHUB_URL = (
    "https://unitedstates.github.io/congress-legislators/legislators-current.json"
)

# -- Server --
# `python server.py` reads HOST/PORT from env so deploy hosts (Railway, Render,
# Fly, etc.) that inject $PORT can be served without code changes. Falls back
# to local dev defaults. Procfile-style hosts that exec `uvicorn server:app`
# directly bypass these — both paths work.
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))