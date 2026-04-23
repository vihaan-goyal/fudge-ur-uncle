"""AI-generated plain-English summaries for congressional committee meetings via OpenAI."""
import openai
from config import OPENAI_API_KEY

_cache: dict = {}


async def get_event_summary(
    title: str,
    chamber: str = "",
    meeting_type: str = "",
    committee: str = "",
    bills: str = "",
) -> str | None:
    if not OPENAI_API_KEY:
        return None

    cache_key = title
    if cache_key in _cache:
        return _cache[cache_key]

    lines = [f"Meeting: {title}"]
    if chamber:
        lines.append(f"Chamber: {chamber}")
    if meeting_type:
        lines.append(f"Type: {meeting_type}")
    if committee:
        lines.append(f"Committee: {committee}")
    if bills:
        lines.append(f"Legislation: {bills}")

    prompt = (
        "You are briefing a citizen activist on a US congressional committee meeting. "
        "Write exactly 2 sentences in plain English: (1) what this meeting is about, "
        "(2) why it matters to everyday citizens. "
        "Be specific and direct. Do not start with 'This meeting' or 'This hearing'.\n\n"
        + "\n".join(lines)
    )

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.choices[0].message.content.strip()
        _cache[cache_key] = summary
        return summary
    except Exception as e:
        print(f"[ai_summary] failed ({e})")
        return None
