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
