import logging
from pydantic import ValidationError
from .models import PurchasedItem, ParsedOrder

logger = logging.getLogger(__name__)


def _parse_item(item):
    raw_name = (item.get("name") or "").strip()
    if not raw_name:
        logger.warning("line item without a name; skipping")
        return None

    try:
        quantity = max(1, int(item.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1

    return PurchasedItem(
        raw_name=raw_name,
        quantity=quantity,
        sku_id=item.get("itemId")
    )


def parse_order(order):
    order_id = order.get("orderId")
    if not order_id:
        logger.warning("order without an orderId; skipping")
        return None
    created_at = order.get("createdAt")
    if not created_at:
        logger.warning("order %s has no createdAt; skipping", order_id)
        return None
    items = [
        parsed
        for parsed in (_parse_item(item) for item in order.get("items", []))
        if parsed is not None
    ]
    if not items:
        logger.warning("order %s has no usable items; skipping", order_id)
        return None
    try:
        # pydantic turns Swiggy's trailing-Z timestamp into an aware UTC
        # datetime. That matters: purchased_at becomes last_purchased_at, and a
        # naive value there shifts every confidence score by the UTC offset
        # without ever raising.
        return ParsedOrder(
            order_id=str(order_id),
            purchased_at=created_at,
            status=order.get("status", ""),
            items=items
        )
    except ValidationError as exc:
        logger.warning("order %s failed validation: %s", order_id, exc)
        return None


def parse_orders(orders):
    parsed = [p for p in (parse_order(order) for order in orders) if p is not None]
    return sorted(parsed, key=lambda order: order.purchased_at)
