import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val

ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")
BLUESKY_IDENTIFIER: str = _require("BLUESKY_IDENTIFIER")
BLUESKY_APP_PASSWORD: str = _require("BLUESKY_APP_PASSWORD")
ETH_PRIVATE_KEY: str = os.getenv("ETH_PRIVATE_KEY", "")
ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "")

POST_INTERVAL_MINUTES: int = int(os.getenv("POST_INTERVAL_MINUTES", "30"))
HUNGER_DECAY_PER_HOUR: float = float(os.getenv("HUNGER_DECAY_PER_HOUR", "3"))
MODEL: str = os.getenv("MODEL", "claude-sonnet-4-6")
