"""
Fudge Ur Uncle - Configuration
================================
Set your API keys here or via environment variables.

Getting your keys (all free):
  1. OpenFEC + Congress.gov: https://api.data.gov/signup/  (one key works for both)
  2. WhoBoughtMyRep:         https://whoboughtmyrep.com/developers
  3. LegiScan:               https://legiscan.com/legiscan  (sign up, free tier = 30K queries/mo)
"""

import os

# -- API Keys --
# A single api.data.gov key works for BOTH OpenFEC and Congress.gov
from dotenv import load_dotenv
load_dotenv()

DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "DEMO_KEY")

WHOBOUGHTMYREP_API_KEY = os.getenv("WHOBOUGHTMYREP_API_KEY", "")

LEGISCAN_API_KEY = os.getenv("LEGISCAN_API_KEY", "")

# -- Base URLs --
OPENFEC_BASE = "https://api.open.fec.gov/v1"
CONGRESS_GOV_BASE = "https://api.congress.gov/v3"
WHOBOUGHTMYREP_BASE = "https://whoboughtmyrep.com/api/v1"
LEGISCAN_BASE = "https://api.legiscan.com"
LEGISLATORS_GITHUB_URL = (
    "https://raw.githubusercontent.com"
    "/unitedstates/congress-legislators/main/legislators-current.json"
)

# -- Server --
HOST = "0.0.0.0"
PORT = 8000
