"""SQLite persistence: users, pantry_items, corrections, order_cache.

Dumb storage layer — no decay math, no LLM calls. See pantry_engine for
confidence scoring and ingester for name normalization.
"""

from .db import get_connection, init_db
from .models import Correction, OrderCache, PantryItem, User, ScoredItem
from .repo import (
    add_correction,
    cache_order,
    delete_pantry_item,
    get_cached_orders,
    get_corrections,
    get_pantry,
    get_user,
    has_order,
    mark_address_confirmed,
    mark_item_out,
    get_pantry_item,
    update_decay_lambda,
    upsert_pantry_item,
    upsert_user,
)
