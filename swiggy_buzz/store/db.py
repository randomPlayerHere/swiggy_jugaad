import sqlite3
from contextlib import closing
from pathlib import Path

from swiggy_buzz import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path=config.DB_PATH):
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db(db_path=config.DB_PATH):
    with closing(get_connection(db_path)) as connection:
        connection.executescript(SCHEMA_PATH.read_text())
        connection.commit()
