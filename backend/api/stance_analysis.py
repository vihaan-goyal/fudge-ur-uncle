"""AI-analyzed voting positions for a legislator via OpenAI."""
import json
import openai
from config import OPENAI_API_KEY
from api.congress_gov import format_vote_lines, format_bill_lines
from api import ai_cache

SAMPLE_STANCES = [
    {
        "topic": "Healthcare",
        "stance": "Consistently supports expanded healthcare access and drug pricing reform.",
        "evidence": "Voted Yea on Prescription Drug Pricing Reform Act; sponsored S.441 Social Security Stabilization Act.",
        "score": "CONSISTENT",
    },
    {
        "topic": "Economy",
        "stance": "Supports middle-class economic measures but splits on minimum wage increases.",
        "evidence": "Voted Yea on infrastructure reauthorization; voted Nay on Federal Minimum Wage Adjustment Act.",
        "score": "MIXED",
    },
    {
        "topic": "Environment",
        "stance": "Voted against clean air modernization, signaling lower priority for environmental regulation.",
        "evidence": "Voted Nay on Clean Air Standards Modernization Act.",
        "score": "INCONSISTENT",
    },
    {
        "topic": "Infrastructure",
        "stance": "Strong supporter of infrastructure investment and modernization.",
        "evidence": "Voted Yea on Infrastructure Investment Reauthorization Act.",
        "score": "CONSISTENT",
    },
]


async def get_stance_analysis(
    cache_key: str,
    name: str,
    party: str,
    chamber: str,
    votes: list[dict],
    sponsored_bills: list[dict],
) -> list[dict] | None:
    if not OPENAI_API_KEY:
        return None

    cached = ai_cache.get(cache_key)
    if cached is not None:
        return cached

    party_label = {"D": "Democrat", "R": "Republican", "I": "Independent"}.get(party, party)

    prompt = (
        f"Analyze the voting record of {name}, a {party_label} serving in the {chamber}.\n\n"
        "SUBSTANTIVE VOTES:\n"
        f"{format_vote_lines(votes)}\n\n"
        "SPONSORED LEGISLATION:\n"
        f"{format_bill_lines(sponsored_bills)}\n\n"
        "Identify 4 to 6 distinct policy areas where this legislator has a demonstrable stance "
        "based only on the votes and bills listed above. For each, return:\n"
        '  "topic": short policy area name (e.g. "Healthcare", "Gun Control", "Climate")\n'
        '  "stance": one sentence describing their actual position based on votes\n'
        '  "evidence": cite 1-2 specific bills with numbers from the data above\n'
        '  "score": one of CONSISTENT (votes align with clear stance), INCONSISTENT (votes contradict expected stance), '
        "MIXED (votes go both ways), or PENDING (only 1 data point)\n\n"
        'Respond ONLY with a JSON object of the form {"stances": [...]} where the array '
        "contains the 4-6 policy entries. No explanation, no markdown, no preamble."
    )

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        # response_format=json_object guarantees a dict, never a bare array.
        stances = parsed.get("stances") if isinstance(parsed, dict) else None
        if not isinstance(stances, list) or not stances:
            print(f"[stance_analysis] Unexpected shape for {cache_key}: keys={list(parsed)[:5] if isinstance(parsed, dict) else type(parsed).__name__}")
            return None
        ai_cache.set(cache_key, stances)
        print(f"[stance_analysis] Generated {len(stances)} stances for {cache_key}")
        return stances
    except Exception as e:
        print(f"[stance_analysis] Failed ({e})")
        return None
