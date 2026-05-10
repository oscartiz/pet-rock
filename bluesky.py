import logging
from dataclasses import dataclass

from atproto import Client
from atproto_client.models.app.bsky.notification.list_notifications import Notification

import db
from tamagotchi import FOOD_EMOJIS

logger = logging.getLogger(__name__)

_FEED_KEYWORDS = {"!feed", "!food", "!eat"}


@dataclass
class MentionFeed:
    actor_did: str
    text: str
    cid: str


def make_client(identifier: str, app_password: str) -> Client:
    client = Client()
    client.login(identifier, app_password)
    return client


def post(client: Client, text: str) -> str:
    """Post to Bluesky. Returns the post URI."""
    response = client.send_post(text=text)
    return response.uri


def get_feed_mentions(client: Client) -> list[MentionFeed]:
    """
    Fetch unseen notifications and return those that contain a feed signal
    (!feed keyword or food emoji). Updates the notification cursor in DB.
    """
    cursor = db.get_state("bluesky_notif_cursor")

    params = {"limit": 50}
    if cursor:
        params["cursor"] = cursor

    try:
        resp = client.app.bsky.notification.list_notifications(params)
    except Exception:
        logger.exception("Failed to fetch Bluesky notifications")
        return []

    if resp.cursor:
        db.set_state("bluesky_notif_cursor", resp.cursor)

    results: list[MentionFeed] = []
    for notif in resp.notifications:
        if notif.reason not in ("mention", "reply"):
            continue
        if notif.is_read:
            continue

        text = _extract_text(notif)
        if _has_feed_signal(text):
            results.append(
                MentionFeed(
                    actor_did=notif.author.did,
                    text=text,
                    cid=notif.cid,
                )
            )

    try:
        client.app.bsky.notification.update_seen({"seenAt": _now_iso()})
    except Exception:
        logger.warning("Could not mark notifications as seen")

    return results


def _has_feed_signal(text: str) -> bool:
    lowered = text.lower()
    if any(kw in lowered for kw in _FEED_KEYWORDS):
        return True
    return any(e in text for e in FOOD_EMOJIS)


def _extract_text(notif: Notification) -> str:
    try:
        record = notif.record
        if hasattr(record, "text"):
            return record.text or ""
    except Exception:
        pass
    return ""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
