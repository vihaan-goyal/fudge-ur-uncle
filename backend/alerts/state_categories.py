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
"""

import re

# (category, list of regex patterns matched against the lowercased title).
# Patterns are word-boundary-aware regex so "tax" doesn't match "taxonomy".
CATEGORY_KEYWORDS = [
    ("environment", [
        r"\bclimate\b",
        r"\bgreenhouse gas",
        r"\bemissions?\b",
        r"\brenewable energy\b",
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
    ]),
    ("healthcare", [
        r"\bprescription drug",
        r"\bpharmaceutical",
        r"\bdrug pricing\b",
        r"\bhealth insurance\b",
        r"\bhealthcare\b",
        r"\bhealth care\b",
        r"\bmedicare\b",
        r"\bmedicaid\b",
        r"\bhospital",
        r"\bnursing home",
        r"\bmental health\b",
        r"\bopioid",
        r"\babortion\b",
        r"\breproductive health",
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
]


_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (cat, [re.compile(p) for p in pats])
    for cat, pats in CATEGORY_KEYWORDS
]


def categorize(title: str, description: str = "") -> str | None:
    """
    Return the first matching category for a bill title (and optional description),
    or None if nothing matches. Match against title first, then description.

    None means "skip this bill" — without a category the topic-match signal T
    is undefined, so the bill can't contribute to alerts.
    """
    if not title and not description:
        return None
    haystack_title = title.lower()
    haystack_desc = description.lower()
    # Title carries more weight — try it alone first.
    for cat, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(haystack_title):
                return cat
    if haystack_desc:
        for cat, patterns in _COMPILED:
            for pat in patterns:
                if pat.search(haystack_desc):
                    return cat
    return None
