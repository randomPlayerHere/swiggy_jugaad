"""Orders missing ingredients: product search, size/price match, cart ops,
checkout. Respects the ₹1000 cart cap and COD-only constraint; never
silent-swaps on stockout; always confirms address before checkout.
"""

from .cart import apply_cap, cart_total
from .checkout import ensure_address_confirmed, place_order
from .matching import pick_variant, resolve_ingredient, resolve_ingredients
from .models import CartLine, OrderSummary, UnresolvedItem

__all__ = [
    "CartLine",
    "UnresolvedItem",
    "OrderSummary",
    "pick_variant",
    "resolve_ingredient",
    "resolve_ingredients",
    "cart_total",
    "apply_cap",
    "ensure_address_confirmed",
    "place_order",
]
