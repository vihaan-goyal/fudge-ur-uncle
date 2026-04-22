"""
Industry -> vote category mapping for topic matching.

The T (topic match) signal uses this table:
- 1.0 if industry is in the PRIMARY list for the vote's category
- 0.5 if industry is in the SECONDARY list (tangential interest)
- 0.0 otherwise

Vote categories match the `category` field on scheduled_votes.
Industries match FEC / OpenSecrets industry codes.

Start simple; expand as we see what data actually comes in.
"""

INDUSTRY_CATEGORY_MAP = {
    "environment": {
        "primary": ["oil_gas", "coal_mining", "electric_utilities", "automotive"],
        "secondary": ["chemical_manufacturing", "agriculture", "construction"],
    },
    "healthcare": {
        "primary": ["pharmaceuticals", "health_insurance", "hospitals", "medical_devices"],
        "secondary": ["biotech", "nursing_homes", "health_professionals", "lawyers_law_firms"],
    },
    "economy": {
        "primary": ["commercial_banks", "securities_investment", "hedge_funds", "private_equity"],
        "secondary": ["accounting", "real_estate", "insurance", "retail", "lawyers_law_firms"],
    },
    "defense": {
        "primary": ["defense_aerospace", "defense_electronics", "private_military"],
        "secondary": ["misc_manufacturing", "computer_software"],
    },
    "infrastructure": {
        "primary": ["construction", "engineering", "cement_concrete", "steel"],
        "secondary": ["electric_utilities", "railroads", "trucking", "transportation_unions"],
    },
    "technology": {
        "primary": ["computer_software", "internet", "telecom_services", "electronics_mfg"],
        "secondary": ["venture_capital", "data_processing", "retail"],
    },
    "labor": {
        "primary": ["labor_unions", "public_sector_unions", "industrial_unions"],
        "secondary": ["building_trades_unions", "transportation_unions"],
    },
    "agriculture": {
        "primary": ["crop_production", "livestock", "food_processing", "agribusiness"],
        "secondary": ["food_beverage", "tobacco"],
    },
}


def topic_match(industry: str, category: str) -> float:
    """
    Return T in [0, 1] — the topic-match signal.

    Returns 1.0 for primary industry matches, 0.5 for secondary, 0.0 otherwise.
    Industry and category are matched case-insensitively, with underscores
    treated as spaces for fuzziness.
    """
    if not industry or not category:
        return 0.0

    ind = industry.lower().replace(" ", "_")
    cat = category.lower().strip()

    mapping = INDUSTRY_CATEGORY_MAP.get(cat)
    if not mapping:
        return 0.0

    if ind in mapping["primary"]:
        return 1.0
    if ind in mapping["secondary"]:
        return 0.5
    return 0.0