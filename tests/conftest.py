"""Test setup: point DB at a tmpfile *before* db is imported, and supply
a fresh-DB fixture for tests that touch SQLite."""
import os
import sys
import tempfile
from pathlib import Path

# Provide dummy env vars so `config` imports succeed.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("BLUESKY_IDENTIFIER", "test.bsky.social")
os.environ.setdefault("BLUESKY_APP_PASSWORD", "test-pass")

# Each test session gets its own DB file.
_TMP_DB = Path(tempfile.mkdtemp(prefix="petrock-test-")) / "test.db"
os.environ["DB_PATH"] = str(_TMP_DB)

# Make the project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture
def fresh_db():
    """Init the DB and wipe feeds/posts/state between tests."""
    import db
    db.init()
    with db._conn() as con:
        con.execute("DELETE FROM feeds")
        con.execute("DELETE FROM posts")
        con.execute("DELETE FROM state")
    yield db
