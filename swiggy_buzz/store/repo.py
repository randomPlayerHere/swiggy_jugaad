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

def upsert_pantry_item(item: PantryItem):
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO pantry_items (user_id, canonical_name, category, last_purchased_at, purchase_qty)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, canonical_name) DO UPDATE SET
                category=excluded.category,
                last_purchased_at=excluded.last_purchased_at,
                purchase_qty=excluded.purchase_qty
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

def delete_pantry_item(user_id: int, canonical_name: str):
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

