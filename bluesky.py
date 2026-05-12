import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from atproto import Client, models
from atproto_client.exceptions import AtProtocolError
from atproto_client.models.app.bsky.notification.list_notifications import Notification

import db
from tamagotchi import has_feed_signal

logger = logging.getLogger(__name__)


@dataclass
class MentionFeed:
    actor_did: str
    text: str
    cid: str
    uri: str
    root_uri: str
    root_cid: str


class BlueskyClient:
    """Thin wrapper around atproto.Client that re-logs in on auth failure."""

    def __init__(self, identifier: str, app_password: str):
        self._identifier = identifier
        self._app_password = app_password
        self._client = Client()
        self._login()

    def _login(self) -> None:
        self._client.login(self._identifier, self._app_password)

    def _call(self, fn):
        try:
            return fn(self._client)
        except AtProtocolError as e:
            msg = str(e).lower()
            if "expired" in msg or "auth" in msg or "token" in msg or "unauthorized" in msg:
                logger.warning("Bluesky auth error (%s) — re-logging in", e)
                self._login()
                return fn(self._client)
            raise

    def send_post(self, text: str) -> str:
        return self._call(lambda c: c.send_post(text=text).uri)

    def send_reply(self, text: str, parent_uri: str, parent_cid: str,
                   root_uri: str, root_cid: str) -> str:
        reply_ref = models.AppBskyFeedPost.ReplyRef(
            parent=models.ComAtprotoRepoStrongRef.Main(uri=parent_uri, cid=parent_cid),
            root=models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid),
        )
        return self._call(lambda c: c.send_post(text=text, reply_to=reply_ref).uri)

    def list_notifications(self, limit: int = 50):
        return self._call(lambda c: c.app.bsky.notification.list_notifications({"limit": limit}))

    def update_seen(self, seen_at: str) -> None:
        self._call(lambda c: c.app.bsky.notification.update_seen({"seenAt": seen_at}))


def make_client(identifier: str, app_password: str) -> BlueskyClient:
    return BlueskyClient(identifier, app_password)


def post(client: BlueskyClient, text: str) -> str:
    return client.send_post(text)


def reply(client: BlueskyClient, text: str, mention: "MentionFeed") -> str:
    return client.send_reply(
        text=text,
        parent_uri=mention.uri,
        parent_cid=mention.cid,
        root_uri=mention.root_uri,
        root_cid=mention.root_cid,
    )


def get_feed_mentions(client: BlueskyClient) -> list[MentionFeed]:
    """
    Fetch the most recent notifications (Bluesky orders newest-first) and
    return mentions/replies that:
      - have not been processed before (by cid), and
      - contain a feed signal (keyword or food emoji).

    A cid-based dedupe set is persisted in the DB so restarts don't double-count.
    The Bluesky `seenAt` marker is also advanced after each successful fetch.
    """
    try:
        resp = client.list_notifications(limit=50)
    except Exception:
        logger.exception("Failed to fetch Bluesky notifications")
        return []

    processed_cutoff = int(db.get_state("notif_processed_cutoff_ts", "0"))
    newest_indexed_ts = processed_cutoff

    results: list[MentionFeed] = []
    for notif in resp.notifications:
        if notif.reason not in ("mention", "reply"):
            continue

        indexed_ts = _parse_indexed_ts(notif.indexed_at)
        if indexed_ts <= processed_cutoff:
            continue
        if indexed_ts > newest_indexed_ts:
            newest_indexed_ts = indexed_ts

        text = _extract_text(notif)
        if has_feed_signal(text):
            root_uri, root_cid = _extract_root_ref(notif)
            results.append(
                MentionFeed(
                    actor_did=notif.author.did,
                    text=text,
                    cid=notif.cid,
                    uri=notif.uri,
                    root_uri=root_uri,
                    root_cid=root_cid,
                )
            )

    if newest_indexed_ts > processed_cutoff:
        db.set_state("notif_processed_cutoff_ts", str(newest_indexed_ts))

    try:
        client.update_seen(_now_iso())
    except Exception:
        logger.warning("Could not mark notifications as seen")

    return results


def _extract_text(notif: Notification) -> str:
    try:
        record = notif.record
        if hasattr(record, "text"):
            return record.text or ""
    except Exception:
        pass
    return ""


def _extract_root_ref(notif: Notification) -> tuple[str, str]:
    """Return (root_uri, root_cid) for replies; the notif itself for top-level posts."""
    try:
        record = notif.record
        reply = getattr(record, "reply", None)
        if reply is not None and getattr(reply, "root", None) is not None:
            return reply.root.uri, reply.root.cid
    except Exception:
        pass
    return notif.uri, notif.cid


def _parse_indexed_ts(indexed_at: str | None) -> int:
    if not indexed_at:
        return int(time.time())
    try:
        s = indexed_at.replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        return int(time.time())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
