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
        r"\baquacultur",
        r"\bwildlife\b",
        r"\bfisher(y|ies)\b",
        r"\bextended producer responsibility\b",
    ]),
    ("healthcare", [
        r"\bprescription drug",
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
    ]),
    ("economy", [
        r"\btax\b",
        r"\btaxes\b",
        r"\btaxation\b",
        r"\bincome tax\b",
        r"\bproperty tax\b",
        r"\bsales tax\b",
        r"\bbudget\b",
        r"\bappropriation",
        r"\bbond authoriz",
        r"\bminimum wage\b",
        r"\bunemployment\b",
        r"\bsmall business",
        r"\bbanking\b",
        r"\binsurance statutes\b",
        r"\binsurance department",
        r"\bfinancial regulation\b",
        r"\bconsumer protection\b",
    ]),
    ("defense", [
        r"\bnational guard\b",
        r"\bveteran",
        r"\bmilitary\b",
        r"\barmed forces\b",
        r"\bdefense\b",
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
    ]),
    ("technology", [
        r"\bdata privacy\b",
        r"\bartificial intelligence\b",
        r"\bcybersecurity\b",
        r"\binternet\b",
        r"\bsocial media\b",
        r"\btelecom",
        r"\bdata broker",
        r"\bbiometric",
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
    ]),
    ("agriculture", [
        r"\bagricult",
        r"\bfarming\b",
        r"\bdairy\b",
        r"\bcrop\b",
        r"\blivestock\b",
        r"\bpesticide",
        r"\bfood safety\b",
        r"\bsnap benefit",
    ]),
    ("housing", [
        r"\baffordable housing\b",
        r"\bhousing\b",
        r"\brent control\b",
        r"\bzoning\b",
        r"\beviction\b",
        r"\bfair housing\b",
        r"\bhomeless",
        r"\blandlord",
        r"\btenant",
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
        r"\bpolling place",
        r"\bballot\b",
        r"\belectoral\b",
        r"\bvoting rights\b",
        r"\bvoter\b",
        r"\bvoters\b",
        r"\belections?\b",
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
