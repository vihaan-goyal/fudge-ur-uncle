"""
FTM `General_Industry` -> our internal industry slug.

The targets here line up with the industry strings used in
`industry_map.py` so the topic-match table works without translation.
"""

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
