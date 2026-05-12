"""
TEE_PEB — autonomous pet rock agent.

Usage:
    python main.py
    python main.py --dry-run     # generate one post locally and print it

On first run with no ETH_PRIVATE_KEY set, a wallet is generated and the
private key is printed. Copy it into your .env before restarting.
"""

import argparse
import logging
import os
import signal
import sys
import time

import anthropic
from apscheduler.schedulers.background import BackgroundScheduler

import bluesky as bsky
import config
import db
import tamagotchi as tama
import wallet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Globals (initialised in main)
# ---------------------------------------------------------------------------
_anthropic_client: anthropic.Anthropic | None = None
_bsky_client = None
_eth_private_key: str = ""


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def job_hunger_decay():
    state = tama.load()
    state = tama.apply_decay(state, config.HUNGER_DECAY_PER_HOUR)
    tama.save(state)
    logger.info("Hunger after decay: %.1f  mood: %s", state.hunger, tama.get_mood(state))


def job_check_mentions():
    if _bsky_client is None:
        return

    mentions = bsky.get_feed_mentions(_bsky_client)
    if not mentions:
        return

    state = tama.load()
    fed_count = 0
    for mention in mentions:
        state, accepted = tama.try_social_feed(state, mention.actor_did, mention.text)
        if not accepted:
            continue
        fed_count += 1
        logger.info("Social feed accepted from %s (+%.0f hunger)", mention.actor_did, tama.SOCIAL_HUNGER_GAIN)
        # Reply to the feeder with a thank-you in the post-feed mood.
        _try_reply_to_feeder(mention, state)

    if fed_count:
        tama.save(state)
        logger.info("Processed %d social feed(s). Hunger now: %.1f", fed_count, state.hunger)


def _try_reply_to_feeder(mention: "bsky.MentionFeed", state: "tama.State") -> None:
    if _bsky_client is None or _anthropic_client is None:
        return
    mood = tama.get_mood(state)
    try:
        import brain
        text = brain.generate_reply(state.hunger, mood, mention.text, _anthropic_client)
    except Exception:
        logger.exception("Brain failed to generate reply for %s", mention.actor_did)
        return
    try:
        uri = bsky.reply(_bsky_client, text, mention)
        logger.info("Replied to %s [%s]: %s  →  %s", mention.actor_did, mood, text[:60], uri)
    except Exception:
        logger.exception("Failed to send reply to %s", mention.actor_did)


def job_check_eth():
    if not _eth_private_key or not config.ETH_RPC_URL:
        return

    txs = wallet.check_incoming(_eth_private_key, config.ETH_RPC_URL)
    if not txs:
        return

    state = tama.load()
    for tx in txs:
        gain = tama.eth_hunger_gain(tx.wei)
        state = tama.apply_eth_feed(state, tx.from_addr, tx.wei)
        logger.info(
            "ETH feed: %s sent %d wei → +%.1f hunger (tx %s)",
            tx.from_addr, tx.wei, gain, tx.tx_hash,
        )

    tama.save(state)
    logger.info("ETH feeds processed. Hunger now: %.1f", state.hunger)


def job_agent_post():
    if _bsky_client is None or _anthropic_client is None:
        logger.warning("Clients not ready — skipping post")
        return

    state = tama.load()
    mood = tama.get_mood(state)
    recent_feeds = db.recent_feed_count(3600)

    try:
        text = brain_generate(state.hunger, mood, recent_feeds)
    except Exception:
        logger.exception("Brain failed to generate post")
        return

    try:
        uri = bsky.post(_bsky_client, text)
        db.log_post(text, mood, state.hunger)
        logger.info("Posted [%s / hunger=%.0f]: %s  →  %s", mood, state.hunger, text[:60], uri)
    except Exception:
        logger.exception("Failed to post to Bluesky")


def brain_generate(hunger: float, mood, recent_feeds: int) -> str:
    import brain
    return brain.generate_post(hunger, mood, recent_feeds, _anthropic_client)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _setup_wallet() -> str:
    key = config.ETH_PRIVATE_KEY
    key_path = db.DB_PATH.parent / "wallet.key"

    if not key and key_path.exists():
        # Persisted wallet on disk (e.g. Fly volume). Reuse instead of
        # regenerating — prevents orphaning any ETH already sent.
        key = key_path.read_text().strip()
        logger.info("Loaded ETH private key from %s", key_path)

    if not key:
        key, address = wallet.generate_wallet()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        print("\n" + "=" * 60)
        print("NEW ETHEREUM WALLET GENERATED")
        print(f"  Address:     {address}")
        print(f"  Private key: {key}")
        print(f"\nKey saved to {key_path} (mode 600).")
        print("On hosts with a persistent volume (e.g. Fly /data), this file")
        print("will be auto-loaded on the next start. Otherwise, copy the key")
        print("into your .env as ETH_PRIVATE_KEY before restarting — the agent")
        print("refuses to continue here so it cannot orphan ETH by generating")
        print("a fresh wallet on the next run.")
        print("=" * 60 + "\n")
        db.set_state("eth_address", address)
        sys.exit(0)

    address = wallet.get_address(key)
    db.set_state("eth_address", address)
    logger.info("Ethereum wallet: %s", address)
    return key


def _run_dry_run() -> None:
    """Generate one post locally and print it. No Bluesky, no wallet, no posting."""
    db.init()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    if db.get_state("hunger") is None:
        tama.save(tama.State(hunger=80.0, last_decay_ts=int(time.time())))

    state = tama.load()
    mood = tama.get_mood(state)
    recent = db.recent_feed_count(3600)

    import brain
    text = brain.generate_post(state.hunger, mood, recent, client)

    print(f"\n[hunger={state.hunger:.0f}  mood={mood}  recent_feeds={recent}]")
    print("-" * 60)
    print(text)
    print("-" * 60 + "\n")


def main():
    global _anthropic_client, _bsky_client, _eth_private_key

    parser = argparse.ArgumentParser(prog="tee_peb")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print one post without connecting to Bluesky or posting.",
    )
    args = parser.parse_args()

    if args.dry_run:
        _run_dry_run()
        return

    db.init()

    _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    logger.info("Connecting to Bluesky as %s …", config.BLUESKY_IDENTIFIER)
    _bsky_client = bsky.make_client(config.BLUESKY_IDENTIFIER, config.BLUESKY_APP_PASSWORD)
    logger.info("Bluesky connected.")

    _eth_private_key = _setup_wallet()

    # Initialise hunger state if first run
    if db.get_state("hunger") is None:
        init_state = tama.State(hunger=80.0, last_decay_ts=int(time.time()))
        tama.save(init_state)
        logger.info("Initialized hunger to 80.")

    scheduler = BackgroundScheduler()
    scheduler.add_job(job_hunger_decay, "interval", minutes=60, id="hunger_decay")
    scheduler.add_job(job_check_mentions, "interval", minutes=15, id="check_mentions")
    scheduler.add_job(job_check_eth, "interval", minutes=15, id="check_eth")
    scheduler.add_job(
        job_agent_post,
        "interval",
        minutes=config.POST_INTERVAL_MINUTES,
        id="agent_post",
    )
    scheduler.start()
    logger.info(
        "Scheduler started. Posting every %d min, checking mentions/ETH every 15 min.",
        config.POST_INTERVAL_MINUTES,
    )

    # Run an immediate post on startup
    logger.info("Running initial post …")
    job_agent_post()

    def _shutdown(_sig, _frame):
        logger.info("Shutting down — waiting for in-flight jobs (up to 30s) …")
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
