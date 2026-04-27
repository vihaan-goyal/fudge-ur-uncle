"""
State-legislator website derivation.

Legiscan's getPerson doesn't return an official site URL, but the promise-scoring
pipeline needs one to scrape policy positions. We fall back to Ballotpedia by
default because its member pages:
  1. Follow a predictable URL pattern (spaces -> underscores)
  2. Exist for the overwhelming majority of state legislators
  3. Usually surface some policy-position text scrape-friendly

Per-state overrides can be added to _STATE_HANDLERS when a more authoritative
caucus or legislature site is known. Returning None from a handler falls through
to the Ballotpedia default.
"""
from typing import Callable, Optional


def _ballotpedia(person: dict) -> Optional[str]:
    name = (person.get("name")
            or f"{person.get('first_name','')} {person.get('last_name','')}".strip())
    if not name:
        return None
    return f"https://ballotpedia.org/{name.strip().replace(' ', '_')}"


# Per-state overrides. Each callable takes the normalized legiscan person dict
# and returns a URL string or None (to fall through to ballotpedia).
_STATE_HANDLERS: dict[str, Callable[[dict], Optional[str]]] = {}


def derive_website(person: dict) -> Optional[str]:
    """Best-effort official/bio site for a state legislator."""
    if not person:
        return None
    state = (person.get("state") or "").upper()
    handler = _STATE_HANDLERS.get(state)
    if handler:
        url = handler(person)
        if url:
            return url
    return _ballotpedia(person)
