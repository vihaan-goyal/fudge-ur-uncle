"""
PAC name -> industry classifier.

FEC data does not include industry codes for PACs. We use a two-tier approach:

1. EXACT MATCHES: hardcoded dictionary of well-known PAC names -> industry.
   These are the big repeat donors across cycles; covers a large % of PAC dollar
   volume even though it's only a small % of total unique PACs.

2. KEYWORD FALLBACK: if no exact match, scan for industry-signaling keywords
   in the PAC name (e.g. "petroleum" -> oil_gas, "bank" -> commercial_banks).

3. UNKNOWN: anything else is tagged "unknown". These still get stored, but
   the T signal in scoring will be 0 so they never produce alerts.

Industry codes here MUST match the keys in alerts/industry_map.py so that
scoring's topic_match() can resolve them.
"""

import re

# -- Tier 1: Exact / near-exact known PACs --
# Case-insensitive match on normalized name (strip "PAC", "INC", "FUND", etc.)
KNOWN_PACS = {
    # Oil & gas
    "exxon mobil corp": "oil_gas",
    "chevron": "oil_gas",
    "marathon oil": "oil_gas",
    "marathon petroleum": "oil_gas",
    "occidental petroleum": "oil_gas",
    "conocophillips": "oil_gas",
    "valero energy": "oil_gas",
    "phillips 66": "oil_gas",
    "bp corporation north america": "oil_gas",
    "koch industries": "oil_gas",
    "halliburton": "oil_gas",
    "american petroleum institute": "oil_gas",

    # Electric utilities
    "duke energy": "electric_utilities",
    "southern company": "electric_utilities",
    "nextera energy": "electric_utilities",
    "edison international": "electric_utilities",

    # Pharmaceuticals
    "pfizer": "pharmaceuticals",
    "merck": "pharmaceuticals",
    "eli lilly": "pharmaceuticals",
    "johnson & johnson": "pharmaceuticals",
    "abbvie": "pharmaceuticals",
    "bristol-myers squibb": "pharmaceuticals",
    "amgen": "biotech",
    "gilead sciences": "biotech",
    "pharmaceutical research and manufacturers": "pharmaceuticals",  # PhRMA
    "phrma": "pharmaceuticals",

    # Health insurance
    "cigna": "health_insurance",
    "unitedhealth group": "health_insurance",
    "elevance health": "health_insurance",
    "anthem": "health_insurance",
    "humana": "health_insurance",
    "aetna": "health_insurance",
    "blue cross blue shield": "health_insurance",
    "americas health insurance plans": "health_insurance",

    # Defense
    "lockheed martin": "defense_aerospace",
    "raytheon": "defense_aerospace",
    "rtx corporation": "defense_aerospace",
    "northrop grumman": "defense_aerospace",
    "boeing": "defense_aerospace",
    "general dynamics": "defense_aerospace",
    "l3harris technologies": "defense_aerospace",
    "textron": "defense_aerospace",

    # Commercial banks
    "jpmorgan chase": "commercial_banks",
    "bank of america": "commercial_banks",
    "wells fargo": "commercial_banks",
    "citigroup": "commercial_banks",
    "goldman sachs": "securities_investment",
    "morgan stanley": "securities_investment",
    "american bankers association": "commercial_banks",

    # Tech (brand names that double as common English words use a more
    # specific key — bare "apple"/"alphabet"/"amazon" would word-match in
    # PAC names like "Big Apple Realtors" or "Alphabet Soup Education").
    "alphabet inc": "internet",
    "google llc": "internet",
    "meta platforms": "internet",
    "facebook": "internet",
    "microsoft": "computer_software",
    "amazon corporate": "internet",
    "amazon.com": "internet",
    "apple inc": "electronics_mfg",
    "oracle corporation": "computer_software",
    "comcast": "telecom_services",
    "at&t": "telecom_services",
    "verizon communications": "telecom_services",

    # Labor unions
    "afl-cio": "labor_unions",
    "afscme": "public_sector_unions",
    "seiu": "public_sector_unions",
    "teamsters": "transportation_unions",
    "uaw": "industrial_unions",
    "american federation of teachers": "public_sector_unions",
    "national education association": "public_sector_unions",
    "carpenters and joiners": "building_trades_unions",
    "ibew": "building_trades_unions",

    # Agriculture
    "american farm bureau": "agribusiness",
    "monsanto": "agribusiness",
    "cargill": "agribusiness",
    "tyson foods": "food_processing",
    "archer daniels midland": "food_processing",
    "nestle": "food_beverage",
    "coca-cola": "food_beverage",

    # Construction / infrastructure
    "caterpillar": "construction",
    "bechtel": "engineering",
    "fluor": "engineering",
    "associated general contractors": "construction",

    # Real estate
    "national association of realtors": "real_estate",

    # Securities / investment
    "blackrock": "securities_investment",
    "citadel": "hedge_funds",
    "carlyle group": "private_equity",
    "kkr": "private_equity",
    "blackstone": "private_equity",
    "investment company institute": "securities_investment",
    "credit suisse": "securities_investment",
    "ubs": "securities_investment",
    "deutsche bank": "commercial_banks",
    "capital one": "commercial_banks",
    "pnc": "commercial_banks",
    "us bank": "commercial_banks",
    "truist": "commercial_banks",

    # Common leadership PACs and party-aligned PACs (hard to classify by industry)
    # These are intentionally NOT mapped to any industry — they're cross-industry
    # money movers that shouldn't trip the topic-match gate.
    # If you want to track them, add a "party" or "leadership" category.

    # Insurance (separate from health insurance)
    "metlife": "insurance",
    "prudential": "insurance",
    "new york life": "insurance",
    "allstate": "insurance",
    "progressive corp": "insurance",
    "liberty mutual": "insurance",
    "national association of insurance and financial advisors": "insurance",
    "independent insurance agents": "insurance",

    # Trade unions
    "international brotherhood of electrical workers": "building_trades_unions",
    "united food and commercial workers": "industrial_unions",
    "ufcw": "industrial_unions",
    "national air traffic controllers": "transportation_unions",
    "air line pilots association": "transportation_unions",
    "alpa": "transportation_unions",
    "national association of letter carriers": "public_sector_unions",
    "communications workers of america": "telecom_services",
    "cwa": "telecom_services",
    "laborers international union": "building_trades_unions",
    "operating engineers": "building_trades_unions",
    "sheet metal workers": "building_trades_unions",
    "plumbers and pipefitters": "building_trades_unions",
    "machinists and aerospace workers": "industrial_unions",

    # Common PAC names without obvious industry signal in the name
    "national beer wholesalers": "food_beverage",
    "wine and spirits wholesalers": "food_beverage",
    "national restaurant association": "food_beverage",
    "national retail federation": "retail",
    "retail industry leaders": "retail",
    "associated builders and contractors": "construction",
    "national association of home builders": "construction",
    "credit union national association": "commercial_banks",
    "mortgage bankers association": "real_estate",
    "national multifamily housing council": "real_estate",
    "national apartment association": "real_estate",
    "ups": "trucking",
    "fedex": "trucking",
    "norfolk southern": "railroads",
    "csx": "railroads",
    "union pacific": "railroads",
    "american trucking associations": "trucking",
    "national rural electric cooperative": "electric_utilities",
    "edison electric institute": "electric_utilities",
    "american gas association": "oil_gas",
    "national association of broadcasters": "telecom_services",
    "ntca rural broadband": "telecom_services",
    "us telecom": "telecom_services",
    "ctia wireless": "telecom_services",

    # Associations / common abbrevs that signal industry
    "ama political": "health_professionals",
    "american medical association": "health_professionals",
    "american dental association": "health_professionals",
    "american hospital association": "hospitals",
    "american college of": "health_professionals",
    "american optometric association": "health_professionals",
    "american association for justice": "lawyers_law_firms",  # trial lawyers
    "association of trial lawyers": "lawyers_law_firms",

    # From CT ingestion top-unknowns
    "janney montgomery scott": "securities_investment",
    "ernst & young": "accounting",
    "american institute of certified public accountants": "accounting",
    "vanguard investments": "securities_investment",
    "honeywell": "defense_aerospace",  # Honeywell's PAC mostly tracks aerospace
    "axon enterprise": "defense_aerospace",  # Tasers/police tech
    "huntington ingalls": "defense_aerospace",  # Naval shipbuilder
    "serco": "defense_aerospace",  # Defense services contractor
    "avangrid": "electric_utilities",
    "title industry": "real_estate",
    "american maritime officers": "transportation_unions",
    "machinists non-partisan": "industrial_unions",  # IAM political arm
}


# -- Tier 2: Keyword -> industry fallback --
# Order matters: first match wins. More specific terms go first.
KEYWORD_RULES = [
    # Oil & gas
    (r"\b(petroleum|exploration|drilling|oilfield|refining)\b", "oil_gas"),
    (r"\b(natural gas|pipeline|midstream|upstream)\b", "oil_gas"),
    (r"\boil\b(?! painting)", "oil_gas"),

    # Utilities
    (r"\belectric (cooperative|utility|power)\b", "electric_utilities"),
    (r"\bedison\b", "electric_utilities"),
    (r"\bpower (company|cooperative|authority)\b", "electric_utilities"),

    # Pharma / biotech
    (r"\b(pharma|pharmaceutical|drugs|biopharm|biologic)\b", "pharmaceuticals"),
    (r"\b(biotech|genomic|therapeutic)\b", "biotech"),

    # Health insurance / hospitals / health professionals
    (r"\bhealth (insurance|plan)\b", "health_insurance"),
    (r"\b(hospital|medical center|health system)\b", "hospitals"),
    (r"\bmedical devices\b", "medical_devices"),
    (r"\bnurs(es|ing|e)\b", "health_professionals"),
    (r"\b(physicians|doctors|surgeons|dentists)\b", "health_professionals"),

    # Defense / aerospace
    (r"\b(aerospace|defense contractor|missile|avionics|military)\b", "defense_aerospace"),

    # Finance
    (r"\b(bank|banking|bancorp|bancshares|bankers)\b", "commercial_banks"),
    (r"\b(credit union)\b", "commercial_banks"),
    (r"\b(securities|investment management|asset management|capital management)\b",
     "securities_investment"),
    (r"\b(hedge fund|hedge funds)\b", "hedge_funds"),
    (r"\b(private equity)\b", "private_equity"),
    (r"\binsurance\b", "insurance"),

    # Tech
    (r"\b(software|technologies|tech corp|technology)\b", "computer_software"),
    (r"\b(internet|online|digital|cloud)\b", "internet"),
    (r"\b(telecom|wireless|broadband|cable)\b", "telecom_services"),

    # Labor unions (catch unions before industries they work in)
    (r"\b(teachers|educators|education association)\b", "public_sector_unions"),
    (r"\b(teamsters|transport workers|airline pilots|truckers)\b",
     "transportation_unions"),
    (r"\b(carpenters|electrical workers|building trades|operating engineers|"
     r"plumbers|sheet metal|laborers union)\b", "building_trades_unions"),
    (r"\b(union|workers union|workers association|brotherhood of)\b", "labor_unions"),

    # Agriculture
    (r"\b(farm|agriculture|agribusiness|crop|livestock|dairy farmers)\b",
     "agribusiness"),
    (r"\b(food processing|beverage|brewers|distillers)\b", "food_processing"),
    (r"\b(restaurant|grocers)\b", "food_beverage"),

    # Real estate
    (r"\b(realtors|real estate|builders|home builders)\b", "real_estate"),
    (r"\b(mortgage|housing)\b", "real_estate"),

    # Transportation
    (r"\b(railroad|railway)\b", "railroads"),
    (r"\b(trucking|truckers)\b", "trucking"),

    # Construction / engineering
    (r"\b(construction|contractors)\b", "construction"),
    (r"\b(engineering|engineers)\b", "engineering"),

    # Retail
    (r"\b(retail|retailers)\b", "retail"),

    # Other extractive
    (r"\btobacco\b", "tobacco"),
    (r"\bcoal\b", "coal_mining"),
    (r"\b(mining|mineral)\b", "coal_mining"),

    # Securities catch-all — require a corporate-context word so PAC names
    # that just describe "investment" as a metaphor don't tag as financial.
    (r"\binvestment (group|company|corp|fund|advisors|partners|associates|holdings|services|institute|council)\b",
     "securities_investment"),
]


# Word-boundary patterns derived from KNOWN_PACS so short tokens like "ups"
# don't match inside longer words ("groups"). re.escape handles brand names
# with metacharacters (e.g. "at&t", "bristol-myers squibb").
_KNOWN_PAC_PATTERNS = [
    (re.compile(r"\b" + re.escape(name) + r"\b"), industry)
    for name, industry in KNOWN_PACS.items()
]


def _normalize(name: str) -> str:
    """Lowercase, strip common suffixes, collapse whitespace.

    Only strips ONE suffix — stripping multiple can be too aggressive
    (e.g. "exxon mobil corp pac" -> "exxon mobil" drops the distinguishing token).
    """
    s = name.lower().strip()
    # Strip trailing org suffixes that don't affect industry. First match wins.
    suffixes = [
        " political action committee", " pac",
        " incorporated", " inc",
        " corporation", " corp",
        " llc", " lp",
        " committee", " fund",
        " co",
    ]
    for suffix in suffixes:
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip()
            break
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def classify(pac_name: str) -> str:
    """
    Return an industry code for this PAC name.

    Returns "unknown" if we can't classify — those donations still get stored,
    but score 0 in the pipeline because topic_match("unknown", anything) = 0.
    """
    if not pac_name:
        return "unknown"

    norm = _normalize(pac_name)

    # Tier 1: word-boundary match against known PAC names
    for pattern, industry in _KNOWN_PAC_PATTERNS:
        if pattern.search(norm):
            return industry

    # Tier 2: keyword fallback
    for pattern, industry in KEYWORD_RULES:
        if re.search(pattern, norm):
            return industry

    return "unknown"


# -- Self-test --
if __name__ == "__main__":
    test_cases = [
        ("Exxon Mobil Corp Political Action Committee", "oil_gas"),
        ("PFIZER INC PAC", "pharmaceuticals"),
        ("Lockheed Martin Employees' PAC", "defense_aerospace"),
        ("American Petroleum Institute PAC", "oil_gas"),
        ("SEIU COPE", "public_sector_unions"),
        ("JPMorgan Chase & Co PAC", "commercial_banks"),
        ("Somebody's Random Local PAC", "unknown"),
        ("National Realtors Assn PAC", "real_estate"),
        ("Chesapeake Energy Exploration PAC", "oil_gas"),
        ("Smith & Jones LLC Pharmaceutical Fund", "pharmaceuticals"),
        ("", "unknown"),
    ]
    ok = 0
    for pac, expected in test_cases:
        got = classify(pac)
        mark = "OK " if got == expected else "FAIL"
        ok += 1 if got == expected else 0
        print(f"  {mark}  {pac!r:60s} -> {got} (expected {expected})")
    print(f"\n  {ok}/{len(test_cases)} passed")