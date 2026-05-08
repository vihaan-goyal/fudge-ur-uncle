"""Regression tests for backend/alerts/state_categories.py.

Two things this file locks in:

1. Newly-added keyword patterns (May 2026 expansion) keep matching the
   real-world federal + state titles that motivated them. Drift on any
   of these would silently regress the alert pool.

2. Procedural / generic titles that should stay uncategorized do — most
   importantly, the "An Act Concerning The State Building Code" case
   that originally drove us to drop the description-fallback path. If
   that one starts matching `education` or anything else, the title-only
   discipline is leaking.

Categories here intentionally line up with `industry_map.py`. New patterns
should generally not need new categories — if a bill genuinely doesn't fit
the existing 13, leaving it uncategorized is the right call.
"""
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from backend.alerts.state_categories import categorize


@pytest.mark.parametrize("title,expected", [
    # --- Pre-existing patterns: smoke check that the basics still work.
    ("An Act Concerning Climate Change Goals.", "environment"),
    ("An Act Concerning Prescription Drug Pricing.", "healthcare"),
    ("An Act Concerning Property Tax Relief.", "economy"),
    ("An Act Concerning Veterans' Benefits.", "defense"),
    ("An Act Concerning Affordable Housing.", "housing"),
    ("An Act Concerning Charter Schools.", "education"),
    ("An Act Concerning Sanctuary Cities.", "immigration"),
    ("An Act Concerning Firearms Background Checks.", "firearms"),
    ("An Act Concerning Absentee Ballots.", "elections"),

    # --- Environment expansion
    ("Emergency Wildfire Fighting Technology Act of 2025.", "environment"),
    ("An Act Concerning Invasive Species Management.", "environment"),
    ("An Act Concerning The Safety Of Energy Generation Sources And Energy Storage Systems.", "environment"),
    ("An Act Concerning The Tire Stewardship Program.", "environment"),
    ("An Act Concerning The Sewage Right-to-know Act And Requiring A Report Concerning Well Contamination Protocols.", "environment"),

    # --- Healthcare expansion
    ("Chronic Disease Flexible Coverage Act.", "healthcare"),
    ("Protect Our Seniors Act.", "healthcare"),
    ("An Act Concerning Senior Citizens.", "healthcare"),
    ("An Act Concerning Elderly Caregivers.", "healthcare"),
    ("An Act Concerning Electronic Nicotine Delivery System And Vapor Product Dealers.", "healthcare"),
    ("An Act Concerning The Statute Of Limitation For Injury Caused By Fraud In The Provision Of Fertility Care And Treatment.", "healthcare"),
    ("An Act Concerning Dentistry.", "healthcare"),
    ("An Act Concerning Social Work Licensure.", "healthcare"),

    # --- Economy expansion
    ("An Act Concerning Insurance Regulation In The State.", "economy"),
    ("An Act Concerning Commercial Financing.", "economy"),
    ("Securities and Exchange Commission Real Estate Leasing Authority Revocation Act.", "economy"),
    ("Chinese Currency Accountability Act of 2025.", "economy"),
    ("China Trade Relations Act of 2025.", "economy"),
    ("An Act Authorizing The Deferral Of A Property Revaluation.", "economy"),
    ("An Act Concerning Differential Mill Rates.", "economy"),
    ("Legislative Line Item Veto Act of 2025.", "economy"),

    # --- Defense expansion
    ("NATO Edge Act.", "defense"),

    # --- Infrastructure expansion
    ("Postal Service Transparency and Review Act.", "infrastructure"),
    ("An Act Expanding Permissible Uses For Town Aid Road Grant Funds.", "infrastructure"),

    # --- Technology expansion
    ("An Act Concerning Breaches Of Security Involving Electronic Personal Information.", "technology"),
    ("An Act Redefining 'Executive Branch Agency' For Purposes Of Data Governance.", "technology"),
    ("Commercial Remote Sensing Amendment Act of 2025.", "technology"),

    # --- Labor expansion
    ("An Act Implementing The Recommendations Of The Labor Department.", "labor"),
    ("No Dollars to Uyghur Forced Labor Act.", "labor"),

    # --- Housing expansion
    ("An Act Concerning The Purchase Of Residential Property By Private Equity Entities.", "housing"),
    ("An Act Authorizing Municipalities To Enforce Certain Blight Regulations Without Providing Notice Or An Opportunity To Remediate.", "housing"),
    ("An Act Concerning Mobile Manufactured Homes And Mobile Manufactured Home Parks.", "housing"),
    ("An Act Allowing Long-term Rental Of Bedrooms In A Single-family Home As Of Right.", "housing"),
    ("An Act Concerning Homeowners Insurance Disclosure.", "housing"),
    ("An Act Concerning The Uniform Relocation Assistance Act.", "housing"),
    ("An Act Concerning Historic Districts And Historic Preservation.", "housing"),

    # --- Elections expansion
    ("An Act Concerning Faithful Presidential Electors.", "elections"),
])
def test_categorize_positive(title, expected):
    assert categorize(title) == expected, (
        f"{title!r} got {categorize(title)!r}, expected {expected!r}"
    )


@pytest.mark.parametrize("title", [
    # The original anchor: title-only discipline must keep "Building Code"
    # out of `education`. Pre-cleanup, the description fallback got it
    # tagged because the policy summary mentioned schools.
    "An Act Concerning The State Building Code.",

    # Generic / procedural titles. Without a clear policy signal these
    # should drop out of the alert pipeline rather than getting tagged
    # arbitrarily.
    "An Act Concerning Planning And Development.",
    "An Act Conveying A Parcel Of State Land To The Town Of North Canaan.",
    "An Act Implementing The Recommendations Of The Majority Leader's Roundtable.",
    "An Act Requiring Annual State Agency Performance Plans.",
    "An Act Implementing The Recommendations Of The Office Of State Ethics For Revisions To The State Codes Of Ethics.",
    "An Act Concerning The Publication Of Municipal Legal Notices.",
    "An Act Implementing The Recommendations Of The Freedom Of Information Commission For Revisions To The Freedom Of Information Act.",

    # Empty / no-input.
    "",
])
def test_categorize_stays_none(title):
    assert categorize(title) is None, (
        f"{title!r} unexpectedly tagged {categorize(title)!r}; should be None"
    )


@pytest.mark.parametrize("title,expected", [
    # Bare "energy" was deliberately excluded — only specific energy
    # contexts should match. This pair regression-tests the choice.
    ("Strategic Energy Coalition Act.", None),  # no specific energy term
    ("An Act Concerning Renewable Energy Procurement.", "environment"),

    # `\bsenior\b` would catch "senior partner" — only `\bseniors\b`
    # (plural) and `\bsenior citizens?\b` are allowed.
    ("An Act Concerning Senior Partner Disclosures.", None),
    ("An Act Concerning Seniors.", "healthcare"),

    # `\bdental\b` matches "dental" but `\bdentist` covers dentistry too.
    ("An Act Concerning Dental Coverage.", "healthcare"),
    ("An Act Concerning Dentistry.", "healthcare"),
])
def test_categorize_boundary_cases(title, expected):
    assert categorize(title) == expected, (
        f"{title!r} got {categorize(title)!r}, expected {expected!r}"
    )
