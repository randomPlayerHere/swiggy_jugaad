import sqlite3
from typing import Optional

from .. import config

# Module-level cached connection
_conn: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    """Open (or reuse) a connection to config.DB_PATH.

    The connection has row_factory = sqlite3.Row, enables foreign keys
    and sets journal_mode = WAL.
    """
    global _conn
    if _conn is not None:
        return _conn

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    # Enable WAL mode
    conn.execute("PRAGMA journal_mode = WAL;")
    _conn = conn
    return _conn