from contextlib import asynccontextmanager

from .models import CartLine, UnresolvedItem
from swiggy_buzz.mcp_client.session import instamart_session
from swiggy_buzz.mcp_client.wrappers import search_products


@asynccontextmanager
async def _ensure_session(session):
    """Yield the caller's session, or open one for the whole batch.

    Mirrors wrappers._ensure_session (private there, so not imported) — the
    point is the same: resolve_ingredients loops over many ingredients, and
    without this every one of them would open its own connection instead of
    sharing one.
    """
    if session is not None:
        yield session
        return
    async with instamart_session() as s:
        yield s


def pick_variant(products: list[dict]) -> tuple[dict, dict] | None:
    pairs = [
        (product, variant)
        for product in products
        for variant in product["variants"]
        if variant["price"] is not None
    ]
    if not pairs:
        return None
    return min(pairs, key=lambda pair: pair[1]["price"])


async def resolve_ingredient(address_id: str, ingredient: str, session=None) -> CartLine | UnresolvedItem:
    results = await search_products(address_id, ingredient, session=session)
    if not results:
        return UnresolvedItem(ingredient=ingredient, reason="no products found", similar=results.similar)

    pair = pick_variant(results.products)
    if not pair:
        return UnresolvedItem(ingredient=ingredient, reason="no variants with price found", similar=results.similar)

    product, variant = pair
    return CartLine(
        ingredient=ingredient,
        spin_id=variant["spin_id"],
        sku_id=variant["sku_id"],
        name=product["name"],
        price=variant["price"],
        qty=1,
    )


async def resolve_ingredients(address_id: str, ingredients: list[str], session=None) -> tuple[list[CartLine], list[UnresolvedItem]]:
    lines: list[CartLine] = []
    unresolved: list[UnresolvedItem] = []
    async with _ensure_session(session) as s:
        for ingredient in ingredients:
            result = await resolve_ingredient(address_id, ingredient, session=s)
            if isinstance(result, CartLine):
                lines.append(result)
            else:
                unresolved.append(result)

    return lines, unresolved

