import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "petrock.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feeds (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT NOT NULL,   -- 'social' or 'eth'
    actor     TEXT NOT NULL,   -- bluesky DID or eth address
    amount    REAL NOT NULL,   -- hunger points granted
    raw       TEXT,            -- original value (wei string or post text)
    ts        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    text           TEXT NOT NULL,
    mood           TEXT NOT NULL,
    hunger_at_post REAL NOT NULL,
    ts             INTEGER NOT NULL
);
"""

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init():
    with _conn() as con:
        con.executescript(_SCHEMA)

# --- state ---

def get_state(key: str, default: str | None = None) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_state(key: str, value: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

# --- feeds ---

def log_feed(source: str, actor: str, amount: float, raw: str = ""):
    with _conn() as con:
        con.execute(
            "INSERT INTO feeds(source,actor,amount,raw,ts) VALUES(?,?,?,?,?)",
            (source, actor, amount, raw, int(time.time())),
        )

def last_social_feed_ts(actor_did: str) -> int:
    """Unix timestamp of the most recent social feed from this DID, or 0."""
    with _conn() as con:
        row = con.execute(
            "SELECT ts FROM feeds WHERE source='social' AND actor=? ORDER BY ts DESC LIMIT 1",
            (actor_did,),
        ).fetchone()
        return row["ts"] if row else 0

def recent_feed_count(seconds: int = 3600) -> int:
    """Number of feed events in the last `seconds` seconds."""
    cutoff = int(time.time()) - seconds
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) as n FROM feeds WHERE ts>=?", (cutoff,)).fetchone()
        return row["n"]

# --- posts ---

def log_post(text: str, mood: str, hunger: float):
    with _conn() as con:
        con.execute(
            "INSERT INTO posts(text,mood,hunger_at_post,ts) VALUES(?,?,?,?)",
            (text, mood, hunger, int(time.time())),
        )
