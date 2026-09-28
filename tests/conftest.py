import sqlite3

import pytest


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
