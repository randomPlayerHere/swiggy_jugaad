"""Address confirmation + the final cart/checkout calls against Swiggy."""

from swiggy_buzz.mcp_client.wrappers import add_to_cart
from swiggy_buzz.mcp_client.wrappers import checkout as swiggy_checkout
from swiggy_buzz.store.repo import get_user

from .cart import cart_total
from .models import CartLine, OrderSummary


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
    # Response nesting under "data" mirrors every other wrapper's pattern
    # (search_products, your_go_to_items), but not yet confirmed against a
    # live checkout call. Verify order_id actually lands here on the first
    # real order.
    payload = result.get("data", result)
    order_id = payload.get("orderId")

    return OrderSummary(
        lines=lines,
        dropped_for_cap=dropped,
        total=cart_total(lines),
        order_id=order_id,
    )
