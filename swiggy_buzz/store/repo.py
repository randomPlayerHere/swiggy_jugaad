from contextlib import closing

from .db import get_connection
from .models import User, PantryItem, Correction, OrderCache

def upsert_user(user: User):
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, household_size, diet, address_confirmed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                household_size=excluded.household_size,
                diet=excluded.diet,
                address_confirmed=excluded.address_confirmed
            """,
            (user.user_id, user.household_size, user.diet, user.address_confirmed),
        )
        connection.commit()
    
def get_user(user_id: int) -> User | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return User.from_row(row) if row else None

def mark_address_confirmed(user_id: int):
    """Flip address_confirmed without touching household_size/diet, unlike
    upsert_user, which overwrites all three columns from whatever User
    instance it's given."""
    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE users SET address_confirmed = 1 WHERE user_id = ?",
            (user_id,),
        )
        connection.commit()

def upsert_pantry_item(item: PantryItem):
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO pantry_items (user_id, canonical_name, category, last_purchased_at, purchase_qty)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, canonical_name) DO UPDATE SET
                category=excluded.category,
                last_purchased_at=excluded.last_purchased_at,
                purchase_qty=excluded.purchase_qty,
                is_out=0
            """,
            (item.user_id, item.canonical_name, item.category, item.last_purchased_at, item.purchase_qty),
        )
        connection.commit()

def get_pantry(user_id: int) -> list[PantryItem]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM pantry_items WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [PantryItem.from_row(row) for row in rows]

def get_pantry_item(user_id: int, canonical_name: str) -> PantryItem | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM pantry_items WHERE user_id = ? AND canonical_name = ?",
            (user_id, canonical_name),
        ).fetchone()
        return PantryItem.from_row(row) if row else None

def mark_item_out(user_id: int, canonical_name: str):
    """Flag an item as out (ran_out_early) without deleting the row, so the
    learned pace multiplier m survives to the next repurchase (MATH.md §5)."""
    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE pantry_items SET is_out = 1 WHERE user_id = ? AND canonical_name = ?",
            (user_id, canonical_name),
        )
        connection.commit()

def delete_pantry_item(user_id: int, canonical_name: str):
    """Genuinely remove an item (and its m). Not used for corrections; see
    mark_item_out() for ran_out_early (MATH.md §5)."""
    with closing(get_connection()) as connection:
        connection.execute(
            "DELETE FROM pantry_items WHERE user_id = ? AND canonical_name = ?",
            (user_id, canonical_name),
        )
        connection.commit()

def update_decay_lambda(user_id: int, canonical_name: str, new_lambda: float):
    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE pantry_items SET decay_lambda = ? WHERE user_id = ? AND canonical_name = ?",
            (new_lambda, user_id, canonical_name),
        )
        connection.commit()

def add_correction(user_id: int, canonical_name: str, direction: str):
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT INTO corrections (user_id, canonical_name, direction) VALUES (?, ?, ?)",
            (user_id, canonical_name, direction),
        )
        connection.commit()

def get_corrections(user_id: int, canonical_name: str) -> list[Correction]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM corrections WHERE user_id = ? AND canonical_name = ? ORDER BY created_at",
            (user_id, canonical_name),
        ).fetchall()
        return [Correction.from_row(row) for row in rows]

def cache_order(user_id: int, order_id: str, raw_json: str):
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO order_cache (user_id, order_id, raw_json) VALUES (?, ?, ?)",
            (user_id, order_id, raw_json),
        )
        connection.commit()

def has_order(user_id: int, order_id: str) -> bool:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT 1 FROM order_cache WHERE user_id = ? AND order_id = ?",
            (user_id, order_id),
        ).fetchone()
        return row is not None

def get_cached_orders(user_id: int) -> list[OrderCache]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM order_cache WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [OrderCache.from_row(row) for row in rows]

_MAX_SQL_PARAMS = 500  # SQLite caps host parameters per statement

def get_cached_skus(raw_names: list[str]) -> dict[str, tuple[str | None, str]]:
    """Known classifications, as {raw_name: (canonical, category)}. Absent = never classified."""
    names = [name for name in dict.fromkeys(raw_names) if name]
    if not names:
        return {}  # "IN ()" is a syntax error in SQLite

    cached: dict[str, tuple[str | None, str]] = {}
    with closing(get_connection()) as connection:
        for start in range(0, len(names), _MAX_SQL_PARAMS):
            chunk = names[start : start + _MAX_SQL_PARAMS]
            placeholders = ",".join("?" * len(chunk))
            rows = connection.execute(
                f"SELECT raw_name, canonical_name, category FROM sku_cache "
                f"WHERE raw_name IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                cached[row["raw_name"]] = (row["canonical_name"], row["category"])
    return cached

def cache_sku(raw_name: str, canonical_name: str | None, category: str):
    """REPLACE not IGNORE: a re-classification is likely a correction worth taking."""
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO sku_cache (raw_name, canonical_name, category) VALUES (?, ?, ?)",
            (raw_name, canonical_name, category),
        )
        connection.commit()

