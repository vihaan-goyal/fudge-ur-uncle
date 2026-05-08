"""Regression tests for backend/alerts/pac_classifier.py.

Locks in three recent fixes:
1. Word-boundary matching on KNOWN_PACS — short tokens like "ups" must not
   match inside longer words ("groups", "startups").
2. UPS / FedEx are corporate logistics PACs, not unions; both should classify
   as `trucking`, not `transportation_unions`.
3. Tightened over-broad KEYWORD_RULES — bare `energy`, `mutual`, and `investment`
   used to drag unrelated PAC names into electric_utilities / insurance /
   securities_investment buckets. They now require corporate-context words.

Also covers a handful of previously-known-good cases so the keyword fallback
doesn't drift.
"""
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from backend.alerts.pac_classifier import classify


@pytest.mark.parametrize("pac_name,expected", [
    # Bug #1: short-token false positives that used to misclassify
    ("Healthcare Groups PAC", "unknown"),       # used to hit "ups" → transportation_unions
    ("Big Apple Realtors PAC", "real_estate"),  # used to hit "apple" → electronics_mfg
    ("Alphabet Soup Education PAC", "unknown"), # used to hit "alphabet" → internet
    ("Subscriber Action Fund", "unknown"),      # used to hit "ubs" → securities_investment

    # Bug #1: short tokens still match when they're standalone
    ("UPS POLITICAL ACTION COMMITTEE", "trucking"),       # also covers Bug #2
    ("FedEx Corp PAC", "trucking"),                       # also covers Bug #2
    ("UBS Americas Inc PAC", "securities_investment"),
    ("CSX Corporation PAC", "railroads"),
    ("SEIU COPE", "public_sector_unions"),

    # Pre-existing keyword fallback paths — should still work
    ("Exxon Mobil Corp Political Action Committee", "oil_gas"),
    ("PFIZER INC PAC", "pharmaceuticals"),
    ("Lockheed Martin Employees' PAC", "defense_aerospace"),
    ("JPMorgan Chase & Co PAC", "commercial_banks"),
    ("Chesapeake Energy Exploration PAC", "oil_gas"),
    ("National Realtors Assn PAC", "real_estate"),

    # Bug #3: bare-keyword false positives that used to misclassify
    ("Mutual Aid Society PAC", "unknown"),         # used to hit "mutual" → insurance
    ("Strategic Energy Coalition PAC", "unknown"), # used to hit "energy" → electric_utilities
    ("Investment in Education PAC", "unknown"),    # used to hit "investment" → securities_investment

    # Bug #3: tightened rules still catch the legitimate cases
    ("Acme Insurance PAC", "insurance"),                  # bare "insurance" still works
    ("Smith Investment Group PAC", "securities_investment"),  # corporate context preserved
    ("Sunbelt Power Cooperative PAC", "electric_utilities"),  # power + utility-shaped suffix

    # Edge cases
    ("", "unknown"),
    ("Somebody's Random Local PAC", "unknown"),
])
def test_classify(pac_name, expected):
    assert classify(pac_name) == expected, (
        f"{pac_name!r} → {classify(pac_name)!r}, expected {expected!r}"
    )
