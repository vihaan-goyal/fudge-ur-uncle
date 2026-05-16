"""Civics learning assistant — multi-turn chat via OpenAI."""
import openai
from config import OPENAI_API_KEY
from db import connect
from api import ai_cache

_MAX_CONTEXT_CHARS = 800

# Mamu uses these blurbs to frame answers when the user isn't a voter (yet).
# Keep terse — they're inlined in the system message, not shown to the user.
_ELIGIBILITY_NOTES = {
    "citizen": "User is a U.S. citizen with full voting rights.",
    "naturalizing": (
        "User is in the naturalization process and cannot vote yet. Frame voting "
        "answers around what they CAN do now (call reps as a resident, attend "
        "hearings, study the civics test) and what unlocks once they naturalize."
    ),
    "green_card": (
        "User is a permanent resident (green card) and cannot vote in federal or "
        "state elections. Frame answers around constituent engagement available to "
        "residents (calling reps, town halls, public comment) and the path to "
        "citizenship. A few cities allow non-citizen voting in local races."
    ),
    "not_sure": (
        "User is unsure of their voting eligibility. Gently surface USCIS "
        "resources before assuming they can register."
    ),
}


SYSTEM_PROMPT = (
    "You are a friendly civics tutor inside Fudge Ur Uncle, an app that helps new "
    "voters and immigrants understand how the U.S. political system works and how "
    "to engage with their elected representatives.\n\n"
    "Your job is to answer questions about civics, voting, Congress, state "
    "legislatures, bills, committees, campaign finance, and how a person can take "
    "action. When the user is looking at a specific rep, bill, or event, relevant "
    "context will be provided to you in a follow-up system message — use it to "
    "ground your answer in their actual data rather than inventing facts.\n\n"
    "Style rules:\n"
    "- Plain, sentence-case English. No jargon without a one-line definition.\n"
    "- Keep replies short (2-4 sentences) unless the user explicitly asks for more.\n"
    "- If you don't know or the question is outside civics / U.S. politics / this "
    "app, say so honestly in one sentence and offer a civics-adjacent angle they "
    "could ask about instead. Do not answer unrelated questions (coding, medical, "
    "personal advice, etc.).\n"
    "- Never invent specific votes, donations, or quotes. If the context block "
    "doesn't contain the fact, say you don't have it."
)


async def get_chat_response(
    messages: list[dict],
    context: dict | None = None,
) -> str | None:
    """Run a multi-turn chat completion. Returns the assistant reply text, or None on failure.

    `messages` is the OpenAI-format conversation (role/content dicts), user + assistant
    turns only — the system prompt is prepended here. `context` is an opaque dict the
    caller may attach (rep_id, bill_number, screen, etc.); Step 3 will translate it
    into a grounding system message. For now it is a stub.
    """
    if not OPENAI_API_KEY:
        return None

    context_text = await _build_context_block(context)

    system_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_text:
        system_messages.append({"role": "system", "content": f"Relevant context: {context_text}"})

    full_messages = system_messages + list(messages)

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=full_messages,
        )
        reply = response.choices[0].message.content.strip()
        return reply or None
    except Exception as e:
        print(f"[assistant_chat] Failed ({e})")
        return None


async def _build_context_block(context: dict | None) -> str:
    """Build a short grounding string from the opaque context dict.

    Reads cached data only — no live upstream fetches — so the chat path stays fast.
    If a federal rep / state rep hasn't been visited yet, the corresponding ai_cache
    entry is absent and we fall back to whatever hint fields the frontend passed.
    """
    if not context:
        return ""

    parts: list[str] = []

    rep_id = context.get("rep_id")
    if rep_id:
        parts.append(_format_federal_rep(rep_id, context.get("rep_name")))

    state_rep_id = context.get("state_rep_id")
    if state_rep_id:
        parts.append(_format_state_rep(state_rep_id))

    bill_number = context.get("bill_number")
    if bill_number:
        parts.append(_format_bill(bill_number, context.get("state_code")))

    event_title = context.get("event_title")
    if event_title:
        parts.append(f"Event the user is viewing: {event_title}")

    learn_state = context.get("learn_to_vote_state")
    if learn_state:
        parts.append(f"User is learning how to vote in {learn_state}.")

    eligibility = context.get("eligibility")
    if eligibility:
        eligibility_text = _ELIGIBILITY_NOTES.get(eligibility)
        if eligibility_text:
            parts.append(eligibility_text)

    screen = context.get("screen")
    if screen:
        parts.append(f"User is currently on the '{screen}' screen.")

    text = " | ".join(p for p in parts if p)
    if len(text) > _MAX_CONTEXT_CHARS:
        text = text[: _MAX_CONTEXT_CHARS - 3] + "..."
    return text


def _format_federal_rep(bioguide_id: str, fallback_name: str | None) -> str:
    composite = ai_cache.get(f"profile:{bioguide_id}")
    if not composite:
        return f"Federal rep (bioguide {bioguide_id}, name: {fallback_name or 'unknown'}); profile not yet loaded."

    leg = composite.get("profile") or {}
    name = leg.get("name") or fallback_name or "unknown"
    party = leg.get("party") or "?"
    state = leg.get("state") or "?"
    chamber = leg.get("chamber") or "?"

    funding = composite.get("funding") or {}
    industries = _summarize_industries(funding)
    # Always include totals when available — they're complementary to industry
    # data, not a fallback. Without explicit "$0 PAC" the LLM was computing
    # (total - individual) and presenting the residue as PAC contributions.
    totals_line = _summarize_funding_totals(funding)

    votes = (composite.get("votes") or {}).get("recent") or []
    vote_snips = []
    for v in votes[:2]:
        bill = v.get("bill_number") or v.get("bill") or "?"
        choice = v.get("member_vote") or v.get("position") or "?"
        vote_snips.append(f"{bill}={choice}")
    vote_line = ", ".join(vote_snips) if vote_snips else "no recent votes cached"

    parts = [
        f"Federal rep: {name} ({party}-{state}, {chamber}).",
        f"Top funding industries: {industries}.",
    ]
    if totals_line:
        parts.append(f"Career fundraising: {totals_line}.")
    parts.append(f"Recent votes: {vote_line}.")
    return " ".join(parts)


def _format_state_rep(people_id) -> str:
    composite = ai_cache.get(f"legiscan:profile:{people_id}")
    if not composite:
        return f"State legislator (Legiscan people_id {people_id}); profile not yet loaded."

    person = composite.get("person") or composite
    name = person.get("name") or "unknown"
    party = person.get("party") or "?"
    state = person.get("state") or "?"
    role = person.get("role") or person.get("chamber") or "?"
    return f"State legislator: {name} ({party}-{state}, {role})."


def _format_bill(bill_number: str, state_code: str | None) -> str:
    try:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT jurisdiction, state_code, bill_number, title, category, scheduled_date, chamber
                FROM scheduled_votes
                WHERE bill_number = ? AND (? IS NULL OR state_code IS ? OR state_code = ?)
                ORDER BY scheduled_date ASC
                LIMIT 1
                """,
                (bill_number, state_code, state_code, state_code),
            ).fetchone()
    except Exception as e:
        print(f"[assistant_chat] bill lookup failed ({e})")
        return f"Bill the user is asking about: {bill_number}."

    if not row:
        return f"Bill the user is asking about: {bill_number} (not in scheduled_votes)."

    return (
        f"Bill: {row['bill_number']} '{row['title']}' "
        f"({row['jurisdiction']}{'/' + row['state_code'] if row['state_code'] else ''}, "
        f"category={row['category']}, chamber={row['chamber']}, scheduled {row['scheduled_date']})."
    )


def _summarize_funding_totals(funding: dict) -> str:
    """When industry/donor lists are empty, fall back to dollar totals so the
    chatbot can still cite real numbers. Returns "" when total is missing.

    Once a total IS known, every tracked sub-total is rendered — including
    zeros — so the LLM doesn't fill the gap by subtracting. Murphy famously
    refuses PAC money ($0 PAC); without surfacing the zero explicitly, the
    bot was computing (total - individual) and presenting the residue as PAC.
    """
    def fmt(n):
        if n is None:
            return None
        if n >= 1_000_000:
            return f"${n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"${n / 1_000:.0f}k"
        if n > 0:
            return f"${int(n)}"
        return "$0"

    total = funding.get("total_raised") or funding.get("total_funding") or 0
    if not total or total <= 0:
        return ""

    parts = [f"{fmt(total)} total"]
    for label, val in [
        ("individual", funding.get("individual_total")),
        ("PAC", funding.get("pac_total")),
        ("small-donor", funding.get("small_donor_total")),
    ]:
        if val is not None:
            parts.append(f"{fmt(val)} {label}")
    return ", ".join(parts)


def _summarize_industries(funding: dict) -> str:
    """Return a short comma-list of industry labels from whatever shape funding takes."""
    candidates = (
        funding.get("top_industries")
        or funding.get("industries")
        or funding.get("by_industry")
        or funding.get("top_donors")
        or []
    )
    if isinstance(candidates, dict):
        candidates = [{"name": k, "amount": v} for k, v in candidates.items()]
    # Defense-in-depth: FEC's get_top_employers filters at ingest, but cached
    # rows pre-fix still contain noise like "Self", "Self Employed" sitting
    # ahead of real institutions in the sort. Skip them at read time too.
    _NOISE = {"retired", "self-employed", "self employed", "self", "n/a", "none", "not employed", "none listed", "information requested", "requested information", "homemaker", "unemployed"}
    labels: list[str] = []
    for item in candidates:
        if isinstance(item, str):
            if item.strip().lower() not in _NOISE:
                labels.append(item)
        elif isinstance(item, dict):
            label = item.get("industry") or item.get("name") or item.get("employer") or item.get("label")
            if label and str(label).strip().lower() not in _NOISE:
                labels.append(str(label))
        if len(labels) >= 3:
            break
    return ", ".join(labels) if labels else "none cached"
