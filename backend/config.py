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
HOST = "0.0.0.0"
PORT = 8000