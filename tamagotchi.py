import math
import time
from dataclasses import dataclass
from typing import Literal

import db

Mood = Literal["thriving", "content", "hungry", "starving", "critical"]

FOOD_EMOJIS = {"🍕", "🍎", "🥕", "🍖", "🍗", "🍔", "🌮", "🍜", "🍰", "🎂", "🍩", "🍪", "🧁", "🌽", "🥐"}
FEED_KEYWORDS = ("!feed", "!food", "!eat")
SOCIAL_FEED_COOLDOWN_SECS = 3600  # 1 feed per user per hour
SOCIAL_HUNGER_GAIN = 10.0


def has_feed_signal(text: str) -> bool:
    lowered = text.lower()
    if any(kw in lowered for kw in FEED_KEYWORDS):
        return True
    return any(e in text for e in FOOD_EMOJIS)

# ETH feeding: hunger gain = clamp(15 + 35 * log10(1 + eth_value), 15, 50)
ETH_GAIN_MIN = 15.0
ETH_GAIN_MAX = 50.0


@dataclass
class State:
    hunger: float
    last_decay_ts: int


def _mood(hunger: float) -> Mood:
    if hunger >= 80:
        return "thriving"
    if hunger >= 55:
        return "content"
    if hunger >= 35:
        return "hungry"
    if hunger >= 15:
        return "starving"
    return "critical"


def load() -> State:
    hunger = float(db.get_state("hunger", "80"))
    last_decay_ts = int(db.get_state("last_decay_ts", str(int(time.time()))))
    return State(hunger=hunger, last_decay_ts=last_decay_ts)


def save(state: State):
    db.set_state("hunger", str(state.hunger))
    db.set_state("last_decay_ts", str(state.last_decay_ts))


def apply_decay(state: State, decay_per_hour: float) -> State:
    now = int(time.time())
    hours_elapsed = (now - state.last_decay_ts) / 3600.0
    lost = decay_per_hour * hours_elapsed
    new_hunger = max(0.0, state.hunger - lost)
    return State(hunger=new_hunger, last_decay_ts=now)


def get_mood(state: State) -> Mood:
    return _mood(state.hunger)


def eth_hunger_gain(wei: int) -> float:
    eth_value = wei / 1e18
    gain = ETH_GAIN_MIN + (ETH_GAIN_MAX - ETH_GAIN_MIN) * math.log10(1 + eth_value * 100)
    return min(ETH_GAIN_MAX, max(ETH_GAIN_MIN, gain))


def try_social_feed(state: State, actor_did: str, text: str) -> tuple[State, bool]:
    """Attempt a social feed. Returns (new_state, was_accepted)."""
    if not has_feed_signal(text):
        return state, False

    last_ts = db.last_social_feed_ts(actor_did)
    if time.time() - last_ts < SOCIAL_FEED_COOLDOWN_SECS:
        return state, False

    new_hunger = min(100.0, state.hunger + SOCIAL_HUNGER_GAIN)
    new_state = State(hunger=new_hunger, last_decay_ts=state.last_decay_ts)
    db.log_feed("social", actor_did, SOCIAL_HUNGER_GAIN, text[:200])
    return new_state, True


def apply_eth_feed(state: State, from_addr: str, wei: int) -> State:
    """Apply an ETH payment as a feed. Always accepted (no cooldown)."""
    gain = eth_hunger_gain(wei)
    new_hunger = min(100.0, state.hunger + gain)
    new_state = State(hunger=new_hunger, last_decay_ts=state.last_decay_ts)
    db.log_feed("eth", from_addr, gain, str(wei))
    return new_state
