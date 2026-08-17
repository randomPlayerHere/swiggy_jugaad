import json
import anyio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from .session import instamart_session
from .errors import SwiggyToolError, SwiggyUnavailable

logger = logging.getLogger(__name__)

# Pagination safety valve: a while-loop that trusts the server to advance its
# own cursor is a hang waiting to happen. Worst case is truncated data, not a
# frozen bot.
_MAX_PAGES = 20

# Retry schedule for transient failures: 1s, 2s, 4s.
_RETRY_ATTEMPTS = 3


@dataclass
class SearchResults:
    """What a product search found.

    Two lists because a stockout is normal: `products` is exact matches,
    `similar` is what Swiggy suggests instead. We never silent-swap, so both
    come back and a human picks.
    """

    products: list[dict] = field(default_factory=list)
    similar: list[dict] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Truthy when there's something to buy."""
        return bool(self.products)


def _slim_product(product: dict) -> dict:
    """Keep only the fields gap_order and the LLM actually use.

    Raw search responses run ~45 KB per query: image URLs, ratings, promo
    flags, delivery estimates. Passing that on burns LLM context on data
    nobody reads. Both spinId and skuId are kept; cart operations need the
    pair, and productId won't do.
    """
    return {
        "name": product.get("displayName"),
        "brand": product.get("brand"),
        "variants": [
            {
                "spin_id": v.get("spinId"),
                "sku_id": v.get("skuId"),
                "size": v.get("quantityDescription"),
                "price": v.get("price", {}).get("offerPrice"),
                "mrp": v.get("price", {}).get("mrp"),
                "max_qty": v.get("maxQuantity"),
                "veg": v.get("vegClassifier") == "VEG_CLASSIFIER_VEG",
            }
            for v in product.get("variations", [])
        ],
    }


def _in_stock_only(products: list[dict]) -> list[dict]:
    """Drop unavailable variants, then products left with nothing buyable.

    Filtering at this boundary means gap_order never has to ask whether a
    product can actually be purchased.
    """
    for p in products:
        p["variations"] = [
            v for v in p.get("variations", []) if v.get("isInStockAndAvailable")
        ]
    return [p for p in products if p["variations"]]


def _unpack(result, tool_name: str) -> dict:
    """Pull the JSON payload out of an MCP tool result.

    Swiggy mixes prose and JSON across content blocks: get_orders answers
    with a sentence followed by the data. Scan for the first parseable
    block rather than trusting content[0].
    """
    if result.isError:
        detail = getattr(result.content[0], "text", "") if result.content else ""
        raise SwiggyToolError(tool_name, detail)
    for block in result.content:
        text = getattr(block, "text", None)
        if not text:
            continue
        text = text.strip()
        if not text.startswith(("{", '[')):
            continue
        try:
            json_result = json.loads(text)
            return json_result
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse JSON from %s: %s", tool_name, exc)
            continue
    raise SwiggyToolError(tool_name, "no JSON payload in response")


async def _call(session, tool_name: str, args: dict) -> dict:
    """Run one tool and hand back its JSON payload."""
    result = await session.call_tool(tool_name, args)
    return _unpack(result, tool_name)


@asynccontextmanager
async def _ensure_session(session=None):
    """Yield the caller's session, or open a temporary one.

    A caller-supplied session is never closed here; it isn't ours to close.
    Lets one bot turn make several calls over a single connection.
    """
    if session is not None:
        yield session
        return
    async with instamart_session() as s:
        yield s


async def fetch_orders(
    count: int = 20,
    order_type: str = "DASH",
    active_only: bool = False,
    session=None,
) -> list[dict]:
    """Recent Instamart orders, each with its items and purchase date.

    Orders carry `createdAt`, which is what pantry_engine's decay curve
    runs on; without it an item has no age and so no confidence.

    Two limits, both verified against the live server:
      * History reaches back ~15 days only. Not a `count` limit; `hasMore`
        comes back false however many you ask for.
      * `orderType` defaults to DASH. INSTAMART is a separate history; use
        fetch_all_orders() for both.
    """
    args = {"count": count, "orderType": order_type, "activeOnly": active_only}
    async with _ensure_session(session) as s:
        data = await _call(s, "get_orders", args)
    return data.get("data", {}).get("orders", [])


async def fetch_all_orders(count: int = 20, session=None) -> list[dict]:
    """Both order histories merged, newest first.

    Opens one session and reuses it across both calls, so this costs a single
    connection rather than two.
    """
    async with _ensure_session(session) as s:
        dash = await fetch_orders(count, "DASH", session=s)
        mart = await fetch_orders(count, "INSTAMART", session=s)
    # Dedupe by orderId before sorting: nothing stops an order appearing in
    # both histories, and a double-counted purchase would inflate the pantry.
    merged = {o.get("orderId"): o for o in dash + mart}
    # .get() not [] — one order missing a timestamp shouldn't sink the batch.
    return sorted(merged.values(), key=lambda o: o.get("createdAt", ""), reverse=True)


async def fetch_addresses(session=None) -> list[dict]:
    """The user's saved delivery addresses, as {id, tag, address}.

    Must run before search_products, which refuses to work without an ID.
    Returns [] when the user has none saved. That's a fact about their
    account, not a failure; callers decide whether zero is a problem.

    get_addresses answers in JSON, under data.addresses, verified against
    the live server, 2026-08.
    """
    async with _ensure_session(session) as s:
        data = await _call(s, "get_addresses", {})
    return [
        {"id": a.get("id"), "tag": a.get("addressTag"), "address": a.get("addressLine")}
        for a in data.get("data", {}).get("addresses", [])
    ]


async def search_products(
    address_id: str, query: str, offset: int = 0, session=None
) -> SearchResults:
    """Buyable products matching `query` at the given address.

    Args are checked here rather than at Swiggy, so a mistake fails
    instantly with a message naming the fix, not a round-trip later.

    Returns SearchResults because Swiggy answers with two sets: what
    matched, and what it suggests instead. Both are needed to offer an
    alternative on a stockout without silently swapping.

    Out-of-stock variants, and products left with none, are dropped; what
    remains is slimmed to the buyable facts (see _slim_product).
    """
    if not address_id:
        raise ValueError("address_id is required — call fetch_addresses() first")
    if not query or not query.strip():
        raise ValueError("query cannot be empty")

    args = {"addressId": address_id, "query": query, "offset": offset}
    async with _ensure_session(session) as s:
        data = await _call(s, "search_products", args)

    payload = data.get("data", {})
    return SearchResults(
        products=[_slim_product(p) for p in _in_stock_only(payload.get("products", []))],
        similar=[
            _slim_product(p) for p in _in_stock_only(payload.get("similarProducts", []))
        ],
    )


async def fetch_go_to_items(address_id: str, session=None) -> list[dict]:
    """The user's regularly-bought items, across every page.

    Reaches further back than get_orders' ~15-day window, so it's the only
    long-range view of what a household actually buys.

    Carries no dates, so it can't feed the decay curve on its own. Treat it
    as evidence of habit, not of when something was bought.

    Not stock-filtered, unlike search_products: whether the store has an
    item today says nothing about whether the household keeps it.
    Filtering here would discard real habits.
    """
    if not address_id:
        raise ValueError("address_id is required — call fetch_addresses() first")

    products: list[dict] = []
    offset = 0
    async with _ensure_session(session) as s:
        for _ in range(_MAX_PAGES):
            data = await _call(
                s, "your_go_to_items", {"addressId": address_id, "offset": offset}
            )
            payload = data.get("data", {})
            page = payload.get("products", [])
            if not page:
                break
            products.extend(page)

            # nextOffset arrives as a string, and "0" is truthy; comparing
            # the parsed number is what actually stops the loop. Bailing
            # when it fails to advance guards against a server that never
            # moves.
            try:
                next_offset = int(payload.get("nextOffset", 0))
            except (TypeError, ValueError):
                break
            if next_offset <= offset:
                break
            offset = next_offset

    return [_slim_product(p) for p in products]


async def add_to_cart(address_id: str, items: list[dict], session=None) -> dict:
    """Set the Instamart cart to exactly `items`, each {"spinId": ..., "quantity": ...}.

    update_cart REPLACES the whole cart rather than appending (verified
    against Builders docs, 2026-08). Call this once with the full set
    gap_order wants to buy, not once per ingredient, or each call wipes
    out the items added by the call before it.

    Only spinId travels here, not skuId. The pair from _slim_product is for
    identifying a variant in search results, but update_cart's own item
    schema only takes spinId + quantity.
    """
    if not address_id:
        raise ValueError("address_id is required — call fetch_addresses() first")
    args = {"selectedAddressId": address_id, "items": items}
    async with _ensure_session(session) as s:
        return await _call(s, "update_cart", args)


async def get_cart(session=None) -> dict:
    """Current Instamart cart: items, bill breakdown, availablePaymentMethods.

    Read-only, no address needed. The bill breakdown is Swiggy's own total;
    prefer it over summing CartLine prices client-side once a cart exists.
    """
    async with _ensure_session(session) as s:
        return await _call(s, "get_cart", {})


async def checkout(address_id: str, session=None) -> dict:
    """Place the order, COD only. Never asks the caller for a payment method,
    since config.py's COD-only constraint means this always sends "Cash".

    Swiggy's own docs mark this "ALWAYS get explicit user confirmation
    before calling this tool". That confirmation is the caller's job, not
    this wrapper's; it fires the instant it's called.
    """
    if not address_id:
        raise ValueError("address_id is required — call fetch_addresses() first")
    args = {"addressId": address_id, "paymentMethod": "Cash"}
    async with _ensure_session(session) as s:
        return await _call(s, "checkout", args)


async def with_retry(operation, attempts: int = _RETRY_ATTEMPTS):
    """Retry a wrapper call on transient failures only.

        orders = await with_retry(lambda: fetch_orders())

    SwiggyUnavailable (network trouble, 5xx) is worth another go.
    SwiggyAuthExpired and SwiggyToolError are not: a dead token stays dead
    and bad arguments stay bad, so those propagate immediately instead of
    making the user wait out a backoff for news we already have.

    Takes a zero-arg callable so each attempt builds a fresh request, and
    for wrappers called without a session, a fresh connection. Don't wrap
    a call that reuses a session you passed in: if that session is what
    broke, retrying on it can't help.
    """
    for attempt in range(attempts):
        try:
            return await operation()
        except SwiggyUnavailable:
            if attempt == attempts - 1:
                raise
            delay = 2**attempt
            logger.warning(
                "Swiggy unavailable, retrying in %ss (attempt %d/%d)",
                delay,
                attempt + 1,
                attempts,
            )
            await anyio.sleep(delay)