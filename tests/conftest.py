import os
import sqlite3

import pytest

# The OpenAI clients are built at import and refuse an empty key. Tests fake
# every LLM call, so any value works; this lets the suite run with no .env.
os.environ.setdefault("NVIDIA_API_KEY", "test-key-unused")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A store.repo wired to a fresh temp SQLite DB for this test."""
    from swiggy_jugaad.store import db as dbmod
    from swiggy_jugaad.store import repo as repo_module

    path = tmp_path / "test.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(repo_module, "get_connection", connect)
    with connect() as conn:
        conn.executescript(dbmod.SCHEMA_PATH.read_text())
        conn.commit()
    return repo_module
