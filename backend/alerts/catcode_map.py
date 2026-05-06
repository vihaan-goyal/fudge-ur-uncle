"""
Catcode -> our internal industry name.

"Catcode" is the OpenSecrets/CRP industry-coding standard. FollowTheMoney
and most other state campaign-finance sources have adopted it. Codes are
4-character strings (5 with sub-industry); we match by 4-char prefix and
fall back to the 1-char sector when the specific code isn't mapped.

Format:
    'X1234' -> ('industry_name', 'fallback_sector_name')

The targets here line up with the industry strings used in
`industry_map.py` so the topic-match table works without translation.

Reference: https://www.opensecrets.org/downloads/crp/CRP_Categories.txt
"""

# Specific 4-char Catcodes -> our industry names.
CATCODE_TO_INDUSTRY = {
    # Energy & Natural Resources
    "E1100": "oil_gas",
    "E1110": "oil_gas",
    "E1120": "oil_gas",
    "E1140": "oil_gas",
    "E1150": "oil_gas",
    "E1160": "oil_gas",
    "E1180": "oil_gas",
    "E1210": "coal_mining",
    "E1300": "electric_utilities",
    "E1500": "electric_utilities",
    "E1600": "chemical_manufacturing",
    "E1700": "chemical_manufacturing",

    # Agriculture
    "A1000": "crop_production",
    "A1100": "crop_production",
    "A1200": "crop_production",
    "A1500": "agribusiness",
    "A2000": "livestock",
    "A4000": "food_processing",
    "A4100": "food_processing",
    "A4200": "food_processing",
    "A6000": "tobacco",

    # Construction
    "C1000": "construction",
    "C1100": "construction",
    "C1200": "engineering",
    "C2100": "cement_concrete",
    "C2200": "steel",
    "C5000": "construction",

    # Defense
    "D2000": "defense_aerospace",
    "D3000": "defense_electronics",
    "D4000": "private_military",
    "D5000": "defense_aerospace",
    "D9000": "defense_aerospace",

    # Communications & Tech
    "B1000": "computer_software",
    "B1200": "telecom_services",
    "B1300": "telecom_services",
    "B1400": "telecom_services",
    "B1500": "internet",
    "B2000": "electronics_mfg",
    "B2100": "electronics_mfg",
    "B2200": "electronics_mfg",
    "B2300": "electronics_mfg",
    "B2400": "data_processing",

    # Finance / Insurance / Real Estate
    "F1000": "securities_investment",
    "F1100": "securities_investment",
    "F1200": "private_equity",
    "F1300": "hedge_funds",
    "F2100": "commercial_banks",
    "F2200": "commercial_banks",
    "F2300": "accounting",
    "F2400": "insurance",
    "F2500": "real_estate",

    # Health
    "H1000": "health_professionals",
    "H1100": "hospitals",
    "H1110": "hospitals",
    "H1130": "nursing_homes",
    "H1300": "health_insurance",
    "H1400": "pharmaceuticals",
    "H1410": "pharmaceuticals",
    "H1420": "pharmaceuticals",
    "H1430": "biotech",
    "H1500": "medical_devices",
    "H2000": "health_professionals",
    "H3000": "health_professionals",

    # Lawyers & lobbyists
    "K1000": "lawyers_law_firms",
    "K1100": "lawyers_law_firms",
    "K1200": "lawyers_law_firms",

    # Labor
    "L1000": "building_trades_unions",
    "L1100": "industrial_unions",
    "L1200": "transportation_unions",
    "L1300": "transportation_unions",
    "L1400": "labor_unions",
    "L1500": "public_sector_unions",
    "L1600": "public_sector_unions",

    # Misc business
    "M1000": "misc_manufacturing",
    "M2000": "misc_manufacturing",
    "M3000": "automotive",
    "M3100": "automotive",
    "N1000": "retail",
    "N1500": "retail",
    "N2000": "food_beverage",
    "T1000": "transportation_unions",
}

# Sector-level fallback (first letter of Catcode) — used only when the 4-char
# code isn't in the table above.
SECTOR_FALLBACK = {
    "A": "agribusiness",
    "B": "computer_software",
    "C": "construction",
    "D": "defense_aerospace",
    "E": "electric_utilities",
    "F": "securities_investment",
    "H": "health_professionals",
    "K": "lawyers_law_firms",
    "L": "labor_unions",
    "M": "misc_manufacturing",
    "N": "retail",
    "T": "transportation_unions",
}


def industry_for_catcode(catcode: str) -> str:
    """Return our industry name for a Catcode. Falls back to sector, then 'unknown'."""
    if not catcode:
        return "unknown"
    code = catcode.strip().upper()
    if len(code) >= 5:
        # Try the 5-char specific code first if you ever extend the table to that level
        if code[:5] in CATCODE_TO_INDUSTRY:
            return CATCODE_TO_INDUSTRY[code[:5]]
    if code[:4] in CATCODE_TO_INDUSTRY:
        return CATCODE_TO_INDUSTRY[code[:4]]
    if code[:1] in SECTOR_FALLBACK:
        return SECTOR_FALLBACK[code[:1]]
    return "unknown"


# FTM/NIMP `General_Industry` strings (returned by gro=d-cci) -> our slugs.
# These are the human-readable names FTM actually returns. Buckets that
# represent self-funding, unknown coding, or non-industry sources map to
# `_ignore` so the ingester drops them — they would just dilute the alert
# pipeline's industry signals.
FTM_NAME_TO_INDUSTRY = {
    # --- non-industry buckets — drop ---
    "Candidate Contributions": "_ignore",     # self-funding
    "Uncoded": "_ignore",
    "Public Subsidy": "_ignore",              # govt match funds
    "Homemakers/Non-income earners": "_ignore",
    "Retired": "_ignore",
    "Civil Servants/Public Officials": "_ignore",

    # --- Energy ---
    "Oil & Gas": "oil_gas",
    "Mining": "coal_mining",
    "Electric Utilities": "electric_utilities",
    "Misc Energy": "electric_utilities",
    "Environmental Svcs/Equipment": "environmental_svcs",
    "Waste Management": "environmental_svcs",
    "Nuclear Energy": "electric_utilities",
    "Alternative Energy Production & Services": "alt_energy",

    # --- Agriculture / Food ---
    "Agricultural Services/Products": "agribusiness",
    "Crop Production & Basic Processing": "crop_production",
    "Dairy": "agribusiness",
    "Food Processing & Sales": "food_processing",
    "Livestock": "livestock",
    "Poultry & Eggs": "livestock",
    "Tobacco & Tobacco Products": "tobacco",
    "Forestry & Forest Products": "forestry",

    # --- Construction ---
    "Construction Services": "construction",
    "Building Materials & Equipment": "construction",
    "General Contractors": "construction",
    "Home Builders": "construction",
    "Special Trade Contractors": "construction",

    # --- Defense ---
    "Defense Aerospace": "defense_aerospace",
    "Defense Electronics": "defense_electronics",
    "Misc Defense": "defense_aerospace",

    # --- Communications & Tech ---
    "Computers/Internet": "computer_software",
    "TV/Movies/Music": "media",
    "Telecom Services": "telecom_services",
    "Telephone Utilities": "telecom_services",
    "Printing & Publishing": "media",
    "Electronics Mfg & Svcs": "electronics_mfg",

    # --- Finance / Insurance / Real Estate ---
    "Securities & Investment": "securities_investment",
    "Commercial Banks": "commercial_banks",
    "Savings & Loans": "commercial_banks",
    "Credit Unions": "commercial_banks",
    "Finance/Credit Companies": "commercial_banks",
    "Insurance": "insurance",
    "Real Estate": "real_estate",
    "Accountants": "accounting",
    "Misc Finance": "securities_investment",

    # --- Health ---
    "Pharmaceuticals & Health Products": "pharmaceuticals",
    "Health Professionals": "health_professionals",
    "Health Services/HMOs": "health_insurance",
    "Hospitals & Nursing Homes": "hospitals",
    "Misc Health": "health_professionals",

    # --- Lawyers & lobbyists ---
    "Lawyers & Lobbyists": "lawyers_law_firms",
    "Lawyers/Law Firms": "lawyers_law_firms",
    "Lobbyists": "lawyers_law_firms",

    # --- Labor ---
    "Building Trade Unions": "building_trades_unions",
    "Industrial Unions": "industrial_unions",
    "Public Sector Unions": "public_sector_unions",
    "Transportation Unions": "transportation_unions",
    "Misc Unions": "labor_unions",

    # --- Misc business / transport / retail ---
    "Misc Manufacturing & Distributing": "misc_manufacturing",
    "Automotive": "automotive",
    "Chemical & Related Manufacturing": "chemical_manufacturing",
    "Steel Production": "steel",
    "Retail Sales": "retail",
    "Food & Beverage": "food_beverage",
    "Restaurants & Drinking Establishments": "food_beverage",
    "Beer, Wine & Liquor": "food_beverage",
    "Air Transport": "airlines",
    "Trucking": "trucking",
    "Sea Transport": "sea_transport",
    "Railroads": "railroads",
    "Business Services": "business_services",
    "General Business": "business_services",
    "Casinos/Gambling": "gambling",
    "Education": "education",
}


def industry_for_ftm_name(industry_name: str) -> str:
    """Map an FTM `General_Industry` string to our internal industry slug.

    Returns "_ignore" for non-industry buckets (self-funding, uncoded, retired,
    public subsidy, etc.) so the caller can skip them. Returns "unknown" for
    industry-shaped names we haven't mapped yet (worth grepping logs for).
    """
    if not industry_name:
        return "unknown"
    key = industry_name.strip()
    if key in FTM_NAME_TO_INDUSTRY:
        return FTM_NAME_TO_INDUSTRY[key]
    return "unknown"
