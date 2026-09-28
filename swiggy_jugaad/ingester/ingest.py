import logging

from .cache import classify_cached
from .models import ParsedOrder, IngestionSummary
from .parse import parse_orders
from .replay import load_replay_orders
from swiggy_jugaad import config
from swiggy_jugaad.mcp_client import fetch_all_orders, run, with_retry
from swiggy_jugaad.store.repo import cache_order, get_user, has_order, upsert_pantry_item
from swiggy_jugaad.store.models import PantryItem

logger = logging.getLogger(__name__)

def collect_raw_names(orders: list[ParsedOrder]) -> list[str]:
    raw_names = []
    for order in orders:
        for item in order.items:
            raw_names.append(item.raw_name)
    return list(dict.fromkeys(raw_names))


def _apply_order(user_id, order, classifications) -> int:
    count = 0
    for item in order.items:
        classification = classifications.get(item.raw_name)
        if classification is None:
            continue
        if not classification.is_food:
            continue
        insert_item = PantryItem(
            id=0,
            user_id=user_id,
            canonical_name=classification.canonical,
            category=classification.category,
            last_purchased_at= order.purchased_at.isoformat(),
            purchase_qty=item.quantity,
            decay_lambda=None,
            is_out=False
        )
        upsert_pantry_item(insert_item)
        count+=1
    return count


def apply_orders(user_id, orders: list[ParsedOrder], classifications) -> tuple[int,int]:
    items_count,order_count = 0,0
    for order in orders:
        # is_delivered first: caching an in-flight order would hide it forever
        if not order.is_delivered:
            continue
        if has_order(user_id, order.order_id):
            continue
        items_count += _apply_order(user_id, order, classifications)
        order_count+=1
        cache_order(user_id, order.order_id, order.model_dump_json())
    return (order_count,items_count)


def _fetch_raw_orders(count: int) -> list[dict]:
    if config.SWIGGY_ORDERS_REPLAY:
        logger.info("replaying sample orders from %s", config.SWIGGY_ORDERS_REPLAY)
        return load_replay_orders(config.SWIGGY_ORDERS_REPLAY)[:count]
    # Auth errors deliberately escape: the bot shows "tap to reconnect".
    return run(lambda: with_retry(lambda: fetch_all_orders(count)))


def ingest_user_orders(user_id: int, count: int = 20) -> IngestionSummary:
    if get_user(user_id) is None:
        raise ValueError(f"user {user_id} is not onboarded; create the users row first")

    parsed = parse_orders(_fetch_raw_orders(count))
    if not parsed:
        logger.info("no usable orders for user %s", user_id)
        return IngestionSummary()

    names = collect_raw_names(parsed)
    classifications = classify_cached(names)
    orders_ingested, items_added = apply_orders(user_id, parsed, classifications)

    summary = IngestionSummary(
        orders_seen=len(parsed),
        orders_ingested=orders_ingested,
        items_added=items_added,
        products_seen=len(names),
        non_food=sum(1 for c in classifications.values() if not c.is_food),
        unclassified=len(names) - len(classifications),
    )
    logger.info("ingest for user %s: %s", user_id, summary)
    return summary





