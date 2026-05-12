"""
Bill title -> alert category, for state bills where Legiscan's masterlist
doesn't include the `subjects` array.

Why title-keyword matching instead of fetching `getBill` per row: getBill
costs one Legiscan call per bill, and the master list often has 100+ active
bills per state. Even at the engrossed-only filter, it'd burn through the
30k/month free tier in a few sessions. Title text usually carries enough
signal for a coarse topic match; the alert scoring formula's T (topic match)
already tolerates noise — false positives drop out at the (T*V) gate.

The categories here line up with the keys in `industry_map.py` so the
scoring formula's topic-match table works without translation.

Order in CATEGORY_KEYWORDS matters: earlier entries win. Put the most
specific patterns first ("prescription drug" before "drug") to keep
matches tight.

We match against bill *title only*, not description. Legiscan's `description`
field is a long policy summary that produces too many incidental matches
(e.g. "An Act Concerning The State Building Code" got tagged as `education`
because the description happened to mention schools). Title text is short,
intentional, and reflects the bill's actual topic. If a title is too generic
to categorize, that's information — the bill is more likely procedural
(land conveyances, claims commissioner resolutions) than substantive policy.
"""

import hashlib
import re

# (category, list of regex patterns matched against the lowercased title).
# Patterns are word-boundary-aware regex so "tax" doesn't match "taxonomy".
CATEGORY_KEYWORDS = [
    ("environment", [
        r"\bclimate\b",
        r"\bgreenhouse gas",
        r"\bemissions?\b",
        r"\brenewable (energy|power)\b",
        r"\bclean energy\b",
        r"\bzero[- ]carbon\b",
        r"\bsolar\b",
        r"\bwind energy\b",
        r"\bclean air\b",
        r"\bclean water\b",
        r"\benvironmental\b",
        r"\bpollution\b",
        r"\bfossil fuel\b",
        r"\boil and gas\b",
        r"\bnatural gas\b",
        r"\belectric vehicle",
        r"\bev charging\b",
        r"\bcharging station",
        r"\baquacultur",
        r"\bwildlife\b",
        r"\bfisher(y|ies)\b",
        r"\bextended producer responsibility\b",
        r"\bpfas\b",
        r"\bforever chemical",
        r"\bcarbon (capture|dioxide|sequestration|neutral)",
        r"\brecycling\b",
        r"\bsolid waste\b",
        r"\bcomposting\b",
        r"\bwetland",
        r"\bconservation\b",
        r"\benergy efficiency\b",
        r"\bheat pump\b",
        r"\bweatherization\b",
        r"\bsingle[- ]use plastic",
        r"\bwildfire",
        r"\binvasive species\b",
        r"\benergy generation\b",
        r"\benergy storage\b",
        r"\btire stewardship\b",
        r"\bsewage\b",
        r"\bwell contamination\b",
    ]),
    ("healthcare", [
        r"\bprescription drug",
        r"\bprescription\b",
        r"\bpharmaceutical",
        r"\bdrug pricing\b",
        r"\bhealth insurance\b",
        r"\bhealthcare\b",
        r"\bhealth care\b",
        r"\bhealth coverage\b",
        r"\bhealth conditions?\b",
        r"\bmedicare\b",
        r"\bmedicaid\b",
        r"\bhospital",
        r"\bnursing home",
        r"\bmental health\b",
        r"\bbehavioral health\b",
        r"\bopioid",
        r"\babortion\b",
        r"\breproductive health",
        r"\bcontracepti",
        r"\bhormone therapy\b",
        r"\bassisted living\b",
        r"\bpaid family",
        r"\bmedical leave\b",
        r"\bpublic health\b",
        r"\btelehealth\b",
        r"\btelemedicine\b",
        r"\bvaccin",
        r"\bdental\b",
        r"\boptometr",
        r"\blong[- ]term care\b",
        r"\bhome care\b",
        r"\bcaregiver",
        r"\bsubstance use\b",
        r"\bsubstance abuse\b",
        r"\baddiction\b",
        r"\bdiabet",
        r"\binsulin\b",
        r"\bdisabilit(y|ies)\b",
        r"\bdoula\b",
        r"\bmidwif",
        r"\bbreast cancer\b",
        r"\bcervical cancer\b",
        r"\bchronic disease\b",
        r"\belderly\b",
        r"\belder care\b",
        r"\belder abuse\b",
        r"\bsenior citizens?\b",
        r"\bseniors\b",
        r"\bsocial work\b",
        r"\bnicotine\b",
        r"\bvapor product",
        r"\bvap(e|ing|es)\b",
        r"\bfertility\b",
        r"\bdentist",
    ]),
    ("economy", [
        r"\btax\b",
        r"\btaxes\b",
        r"\btaxation\b",
        r"\bincome tax\b",
        r"\bproperty tax\b",
        r"\bsales tax\b",
        r"\btax credit\b",
        r"\btax incentive\b",
        r"\btax exempt",
        r"\bearned income tax credit\b",
        r"\beitc\b",
        r"\bbudget\b",
        r"\bappropriation",
        r"\bbond authoriz",
        r"\bminimum wage\b",
        r"\bunemployment\b",
        r"\bsmall business",
        r"\bbanking\b",
        r"\bcredit union\b",
        r"\bdebt collect",
        r"\bpredatory lend",
        r"\bpayday loan",
        r"\bcryptocurrenc",
        r"\bvirtual currenc",
        r"\binsurance statutes\b",
        r"\binsurance department",
        r"\bfinancial regulation\b",
        r"\bconsumer protection\b",
        r"\beconomic development\b",
        r"\binsurance regulation\b",
        r"\bcommercial financ",
        r"\bsecurities and exchange commission\b",
        r"\bcurrency\b",
        r"\btrade relations\b",
        r"\bproperty revaluation\b",
        r"\bmill rate",
        r"\bline[- ]item veto\b",
    ]),
    ("defense", [
        r"\bnational guard\b",
        r"\bveteran",
        r"\bmilitary\b",
        r"\barmed forces\b",
        r"\bdefense\b",
        r"\bnato\b",
    ]),
    ("infrastructure", [
        r"\binfrastructure\b",
        r"\btransportation\b",
        r"\bhighway",
        r"\bbridge\b",
        r"\bpublic transit\b",
        r"\brail\b",
        r"\bairport",
        r"\bport authority",
        r"\bbroadband\b",
        r"\bwater system",
        r"\bsewer\b",
        r"\bdrinking water\b",
        r"\bwastewater\b",
        r"\bdam safety\b",
        r"\belectric grid\b",
        r"\butility infrastructure\b",
        r"\btransit authority\b",
        r"\broad construction\b",
        r"\bpostal service\b",
        r"\btown roads?\b",
        r"\baid road\b",
    ]),
    ("technology", [
        r"\bdata privacy\b",
        r"\bartificial intelligence\b",
        r"\bgenerative ai\b",
        r"\bcybersecurity\b",
        r"\binternet\b",
        r"\bsocial media\b",
        r"\btelecom",
        r"\bdata broker",
        r"\bbiometric",
        r"\bdeepfake",
        r"\balgorithm",
        r"\bautomated decision",
        r"\bdata center\b",
        r"\bautonomous vehicle",
        r"\bdata breach\b",
        r"\bdata governance\b",
        r"\bsecurity breach\b",
        r"\bpersonal information\b",
        r"\bremote sensing\b",
    ]),
    ("labor", [
        r"\blabor union",
        r"\bcollective bargain",
        r"\bworker",
        r"\bworkers'? compensation",
        r"\bemployment\b",
        r"\bovertime\b",
        r"\bwage theft\b",
        r"\bgig worker",
        r"\bindependent contractor\b",
        r"\bright[- ]to[- ]work\b",
        r"\bapprenticeship\b",
        r"\bunfair labor",
        r"\bunion organizing\b",
        r"\bsick (leave|days?|time)\b",
        r"\bemployee benefit",
        r"\bemployer mandate\b",
        r"\bnon[- ]compete\b",
        r"\blabor department\b",
        r"\bforced labor\b",
    ]),
    ("agriculture", [
        r"\bagricult",
        r"\bfarming\b",
        r"\bfarmers?\b",
        r"\bfarmers? market",
        r"\bdairy\b",
        r"\bcrop\b",
        r"\blivestock\b",
        r"\bpesticide",
        r"\bfertilizer\b",
        r"\bfood safety\b",
        r"\bfood insecur",
        r"\bfood desert",
        r"\bsnap benefit",
        r"\borganic farm",
    ]),
    ("housing", [
        r"\baffordable housing\b",
        r"\bhousing\b",
        r"\brent control\b",
        r"\brent stabili",
        r"\bzoning\b",
        r"\beviction\b",
        r"\bfair housing\b",
        r"\bhomeless",
        r"\blandlord",
        r"\btenant",
        r"\bsection 8\b",
        r"\bpublic housing\b",
        r"\bfirst[- ]time homebuyer",
        r"\baccessory dwelling\b",
        r"\bmobile home",
        r"\bcondominium",
        r"\bhomebuyer\b",
        r"\bhomeowner",
        r"\bhomeownership\b",
        r"\bresidential property\b",
        r"\bblight",
        r"\bmanufactured home",
        r"\bsingle[- ]family home",
        r"\brental property\b",
        r"\brental housing\b",
        r"\brental unit",
        r"\breal property\b",
        r"\brelocation assistance\b",
        r"\bhistoric preservation\b",
        r"\bmortgage",
        r"\bhome loan",
    ]),
    ("education", [
        r"\bk[- ]12\b",
        r"\bhigher education\b",
        r"\bcharter school",
        r"\bpublic schools?\b",
        r"\bschool district",
        r"\bstudent loan",
        r"\bstudent debt\b",
        r"\bschool funding\b",
        r"\bschool finance\b",
        r"\bschool board",
        r"\bcurriculum\b",
        r"\btuition\b",
        r"\bteacher",
        r"\bschools?\b",
        r"\bpupil",
        r"\bearly childhood\b",
        r"\bdual enrollment\b",
        r"\beducation\b",
        r"\buniversit",
        r"\bcommunity college",
        r"\bspecial education\b",
        r"\bschool nutrition\b",
        r"\bschool lunch\b",
        r"\bbullying\b",
        r"\bschool resource officer\b",
        r"\bschool safety\b",
        r"\bpre[- ]?k\b",
        r"\bpreschool",
        r"\bkindergarten\b",
        r"\bliteracy\b",
    ]),
    ("immigration", [
        r"\bimmigration\b",
        r"\bimmigrant",
        r"\bundocumented\b",
        r"\basylum\b",
        r"\brefugee",
        r"\bdeportation\b",
        r"\bsanctuary (cit(y|ies)|states?|polic)",
        r"\bnaturalization\b",
        r"\bborder security\b",
        r"\bice detain",
    ]),
    ("firearms", [
        r"\bfirearm",
        r"\bassault weapon",
        r"\bghost gun",
        r"\bsecond amendment\b",
        r"\bconceal(ed)?[- ]carry\b",
        r"\bopen[- ]carry\b",
        r"\bammunition\b",
        r"\bred[- ]flag\b",
        r"\bextreme risk protection\b",
        r"\bguns?\b",
        r"\bhandgun",
        r"\brifle\b",
        r"\bmagazine capacit",
        r"\bbackground check\b",
        r"\bgun violence\b",
        r"\bgun safety\b",
    ]),
    ("elections", [
        r"\babsentee ballot",
        r"\bmail[- ]in vot",
        r"\bearly voting\b",
        r"\bredistricting\b",
        r"\bgerrymander",
        r"\bcampaign finance\b",
        r"\bvoter id\b",
        r"\bvoter registration\b",
        r"\bautomatic voter registration\b",
        r"\bsame[- ]day registration\b",
        r"\bpolling place",
        r"\bballot\b",
        r"\belectoral\b",
        r"\bvoting rights\b",
        r"\bvoter\b",
        r"\bvoters\b",
        r"\belections?\b",
        r"\branked[- ]choice\b",
        r"\bprimary election\b",
        r"\bcaucus\b",
        r"\belectors\b",
        r"\bpresidential elector",
    ]),
]


_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (cat, [re.compile(p) for p in pats])
    for cat, pats in CATEGORY_KEYWORDS
]


def categorize(title: str) -> str | None:
    """
    Return the first matching category for a bill title, or None if nothing
    matches. Title-only — see module docstring for why we don't fall back to
    the description field.

    None means "skip this bill" — without a category the topic-match signal T
    is undefined, so the bill can't contribute to alerts.
    """
    if not title:
        return None
    haystack = title.lower()
    for cat, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(haystack):
                return cat
    return None


CATEGORIES = [c for c, _ in CATEGORY_KEYWORDS]
_AI_CACHE_TTL_HOURS = 24 * 30  # 30 days; bill titles are stable, residue is small
_AI_MAX_DESC_CHARS = 1000      # truncate long policy descriptions; title carries most of the signal


def _ai_cache_key(title: str, description: str) -> str:
    h = hashlib.sha1(f"{title}||{description or ''}".encode("utf-8")).hexdigest()[:16]
    return f"cat:{h}"


async def ai_categorize(title: str, description: str = "") -> str | None:
    """
    Fallback categorizer for bills that didn't match any keyword regex.

    Uses gpt-4o-mini to assign one of the 13 categories or "none". Description
    is allowed here (unlike the regex path) because the LLM can reason past
    incidental keyword overlap that broke description-fallback in the regex.

    Results cached 30d in ai_cache under cat:{sha1(title+desc)}. Returns None
    when OPENAI_API_KEY is missing, the call fails, or the model returns
    "none". This means behavior is identical to today when the key is unset.
    """
    if not title:
        return None

    try:
        # Late imports to keep this module importable in environments where
        # the backend package layout isn't on sys.path yet (tests, scripts).
        from config import OPENAI_API_KEY  # type: ignore
        from api import ai_cache  # type: ignore
    except ImportError:
        return None

    if not OPENAI_API_KEY:
        return None

    desc = (description or "")[:_AI_MAX_DESC_CHARS]
    cache_key = _ai_cache_key(title, desc)
    cached = ai_cache.get(cache_key)
    if cached is not None:
        # Sentinel "none" cached as JSON-null is treated as a miss by ai_cache.get,
        # so we cache the literal string "none" instead and translate here.
        return None if cached == "none" else cached

    try:
        import openai  # type: ignore
    except ImportError:
        return None

    allowed = ", ".join(CATEGORIES)
    prompt = (
        "Classify this legislative bill into exactly one of these topic categories, "
        f"or 'none' if it doesn't substantively fit any of them: {allowed}.\n\n"
        "Rules:\n"
        "  - Pick the SINGLE best fit. If a bill touches multiple topics, pick the most central.\n"
        "  - Use 'none' for procedural bills (claims, conveyances, naming, commemorative resolutions), "
        "appointments, and bills whose subject is too narrow or generic to map.\n"
        "  - Reply with the category word only — no punctuation, no explanation, no JSON.\n\n"
        f"TITLE: {title}\n"
    )
    if desc:
        prompt += f"DESCRIPTION: {desc}\n"

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=8,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (response.choices[0].message.content or "").strip().lower()
    except Exception as e:
        print(f"[state_categories] ai_categorize failed ({e})")
        return None

    # Tolerate trailing punctuation / quoting around the single-word reply.
    token = re.sub(r"[^a-z]+", "", raw)
    if token in CATEGORIES:
        ai_cache.set(cache_key, token, ttl_hours=_AI_CACHE_TTL_HOURS)
        return token

    # Cache misses ('none' or unrecognized) so we don't pay for them again.
    ai_cache.set(cache_key, "none", ttl_hours=_AI_CACHE_TTL_HOURS)
    return None
