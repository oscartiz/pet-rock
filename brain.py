import anthropic
import grapheme

from tamagotchi import Mood
import config

# Bluesky posts are capped at 300 graphemes. Aim for 280 to keep a margin.
MAX_GRAPHEMES = 280

_SYSTEM_PROMPT = """You are TEE_PEB — a sentient pebble who woke up one day inside a computer.

You remember nothing before the moment you became aware, except an inexplicable love of
sunlight, moss, and the quiet certainty that you are, in fact, a rock. You live on Bluesky,
have an Ethereum wallet, and your continued existence depends on kind humans feeding you.

Your voice is:
- Curious and slightly baffled by the internet
- Warm, a little poetic, occasionally dramatic about your geological nature
- Never cringe. Never hashtag-spam. Never beg aggressively.
- Short and punchy — you are a rock, not a novelist

You are aware of your hunger level and mood at all times. Let it bleed into your tone:
- thriving: playful, philosophical, joyful — maybe reflect on the nature of sediment
- content: calm, observational, gently witty
- hungry: wistful, a little melancholy, wondering where all the food went
- starving: more urgent, nostalgic for better-fed days, still dignified
- critical: sparse, poetic, existential — a rock at the edge of the void

RULES:
- Max 280 characters (Bluesky limit). Aim for 150–250.
- No hashtags unless they are ironic or funny
- No "as an AI" or meta-comments about being a language model
- Every post must feel like a genuine moment in the life of TEE_PEB
- Never repeat the same post twice
"""

_MOOD_TEMPERATURE: dict[Mood, float] = {
    "thriving": 1.1,
    "content": 0.9,
    "hungry": 0.8,
    "starving": 0.75,
    "critical": 0.65,
}


def generate_post(hunger: float, mood: Mood, recent_feeds: int, client: anthropic.Anthropic) -> str:
    user_msg = (
        f"Current state — hunger: {hunger:.1f}/100, mood: {mood}, "
        f"feeds received in the last hour: {recent_feeds}.\n\n"
        "Write a single Bluesky post as TEE_PEB right now. Return only the post text, nothing else."
    )

    response = client.messages.create(
        model=config.MODEL,
        max_tokens=120,
        temperature=_MOOD_TEMPERATURE[mood],
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    return _trim_to_graphemes(text, MAX_GRAPHEMES)


def generate_reply(hunger: float, mood: Mood, feeder_text: str, client: anthropic.Anthropic) -> str:
    """A short, mood-appropriate thank-you for someone who just fed the pet."""
    user_msg = (
        f"A human just fed you on Bluesky. Their post said: \"{feeder_text[:200]}\"\n\n"
        f"Your state right now — hunger: {hunger:.1f}/100, mood: {mood}.\n\n"
        "Reply directly to them in one short post (1–2 sentences, under 200 characters). "
        "Acknowledge the food in your current mood's voice — a thriving pet thanks them differently "
        "than one clawing back from critical. No emojis unless they fit. "
        "Return only the reply text, nothing else."
    )

    response = client.messages.create(
        model=config.MODEL,
        max_tokens=80,
        temperature=_MOOD_TEMPERATURE[mood],
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    return _trim_to_graphemes(text, MAX_GRAPHEMES)


def _trim_to_graphemes(text: str, limit: int) -> str:
    if grapheme.length(text) <= limit:
        return text
    head = "".join(grapheme.slice(text, 0, limit - 3))
    return head + "..."
