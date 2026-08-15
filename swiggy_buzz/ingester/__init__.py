"""Pulls Instamart order history and normalizes item names to canonical
ingredients (LLM-assisted, cached in SQLite so each SKU is normalized once).
"""

from swiggy_buzz.ingester.cache import classify_cached
from swiggy_buzz.ingester.ingest import (
    apply_orders,
    collect_raw_names,
    ingest_user_orders,
)
from swiggy_buzz.ingester.models import IngestionSummary, ParsedOrder, PurchasedItem
from swiggy_buzz.ingester.normalize import Classification, classify
from swiggy_buzz.ingester.parse import parse_order, parse_orders
from swiggy_buzz.ingester.vocabulary import SKIP, VOCABULARY, category_for

__all__ = [
    "ingest_user_orders",
    "IngestionSummary",
    "parse_order",
    "parse_orders",
    "ParsedOrder",
    "PurchasedItem",
    "collect_raw_names",
    "apply_orders",
    "classify",
    "classify_cached",
    "Classification",
    "VOCABULARY",
    "SKIP",
    "category_for",
]
