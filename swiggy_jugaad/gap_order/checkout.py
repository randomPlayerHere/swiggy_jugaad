"""Address confirmation + the final cart/checkout calls against Swiggy."""

import logging

from swiggy_jugaad.mcp_client.wrappers import add_to_cart
from swiggy_jugaad.mcp_client.wrappers import checkout as swiggy_checkout
from swiggy_jugaad.store.repo import get_user

from .cart import cart_total
from .models import CartLine, OrderSummary

logger = logging.getLogger(__name__)


def _order_id(result: dict) -> str | None:
    """Where the order id lands in a checkout response isn't confirmed
    against a live call yet (see place_order), so look in the likely spots
    rather than bet on one. None is a valid answer: the order still went
    through, we just can't name it."""
    for payload in (result.get("data"), result):
        if not isinstance(payload, dict):
            continue
        for key in ("orderId", "order_id", "id"):
            if payload.get(key):
                return str(payload[key])
    return None


def ensure_address_confirmed(user_id: int) -> None:
    """Refuse to proceed unless the household has already confirmed a
    delivery address (store.models.User.address_confirmed); CLAUDE.MD:
    always confirm delivery address before checkout. Driving that
    confirmation is the bot layer's job; this just enforces it happened.
    """
    user = get_user(user_id)
    if user is None or not user.address_confirmed:
        raise ValueError("delivery address not confirmed — confirm it before checkout")


async def place_order(
    user_id: int,
    address_id: str,
    lines: list[CartLine],
    dropped: list[CartLine],
    session=None,
) -> OrderSummary:
    """Push `lines` into the real Swiggy cart, then check out COD.

    Caller must already have explicit user confirmation in hand. checkout()
    fires the instant it's called, per Swiggy's own docs; there's no
    dry-run step to lean on.
    """
    ensure_address_confirmed(user_id)

    items = [{"spinId": line.spin_id, "quantity": line.qty} for line in lines]
    await add_to_cart(address_id, items, session=session)

    result = await swiggy_checkout(address_id, session=session)
    # Logged in full until the response shape is confirmed against a live
    # checkout; see _order_id.
    logger.info("checkout response for user %s: %r", user_id, result)
    order_id = _order_id(result)

    return OrderSummary(
        lines=lines,
        dropped_for_cap=dropped,
        total=cart_total(lines),
        order_id=order_id,
    )
