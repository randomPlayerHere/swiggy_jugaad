"""The LLM-facing menu of actions (bot/agent.py dispatches tool calls here).

Each function is a household-meaningful action, built by composing the
lower-level modules (store, ingester, pantry_engine, recipe, gap_order,
mcp_client) together with our own policy: the ₹1000 cap, the re-ask-address
rule, and the build-cart/confirm-cart split (see bot/prompts.py). The
functions in mcp_client.wrappers are never exposed to the model directly —
this file is the only thing it gets to call.

user_id is always a real Python argument here, but TOOL_SCHEMAS never
includes it as a parameter — dispatch() binds it from the session, so the
model can never choose which household it's acting on.
"""

from datetime import datetime, timezone

from swiggy_buzz.gap_order import CartLine, apply_cap, cart_total, place_order, resolve_ingredients
from swiggy_buzz.ingester import ingest_user_orders
from swiggy_buzz.mcp_client import fetch_addresses, instamart_session, run
from swiggy_buzz.pantry_engine import record_correction
from swiggy_buzz.pantry_engine.execution import score_entire_pantry
from swiggy_buzz.recipe import load_recipes_from_dicts, rank_recipes
from swiggy_buzz.store.models import User
from swiggy_buzz.store.repo import get_user, mark_address_confirmed, upsert_user

from .session_state import PendingOrder, get_or_create_state

# Loaded once at import, like ingester/normalize.py's SYSTEM_PROMPT — a
# recipe DB read on every suggest_recipes() call would be wasted work.
_RECIPES = load_recipes_from_dicts()


def onboard_user(user_id: int, household_size: int | None = None, diet: str | None = None) -> dict:
    """Create or update the household. Read-modify-write: upsert_user
    overwrites household_size/diet/address_confirmed together, so calling
    this again later (e.g. household size changed) without carrying the
    existing row forward would silently reset whatever the LLM didn't
    mention this time.
    """
    existing = get_user(user_id)
    merged = User(
        user_id=user_id,
        household_size=household_size if household_size is not None else (existing.household_size if existing else 1),
        diet=diet if diet is not None else (existing.diet if existing else None),
        address_confirmed=existing.address_confirmed if existing else False,
        created_at=existing.created_at if existing else "",
    )
    upsert_user(merged)
    return {"household_size": merged.household_size, "diet": merged.diet}


def list_addresses(user_id: int) -> list[dict]:
    """Fresh from Swiggy every call, never cached — the household is meant
    to (re)pick before every gap order (prompts.py rule 3)."""
    return run(lambda: fetch_addresses())


def sync_orders(user_id: int, count: int = 20) -> dict:
    summary = ingest_user_orders(user_id, count)
    return {
        "orders_seen": summary.orders_seen,
        "orders_ingested": summary.orders_ingested,
        "items_added": summary.items_added,
        "products_seen": summary.products_seen,
        "non_food": summary.non_food,
        "unclassified": summary.unclassified,
    }


def get_pantry_status(user_id: int) -> list[dict]:
    scored = score_entire_pantry(user_id, datetime.now(timezone.utc))
    if scored is None:
        return []
    return [
        {"name": s.pantry_item.canonical_name, "confidence": round(s.confidence_score, 2), "bucket": s.bucket}
        for s in scored
    ]


def suggest_recipes(user_id: int, top_n: int = 3) -> list[dict]:
    user = get_user(user_id)
    if user is None:
        return []
    scored = score_entire_pantry(user_id, datetime.now(timezone.utc)) or []
    ranked = rank_recipes(_RECIPES, scored, user.diet)
    return [
        {"recipe_id": r.id, "name": r.name, "score": round(s, 2), "missing_ingredients": missing}
        for r, s, missing in ranked[:top_n]
    ]


def _line_dict(line: CartLine) -> dict:
    return {"ingredient": line.ingredient, "name": line.name, "price": line.price, "qty": line.qty}


async def _resolve_and_cap(address_id: str, ingredients: list[str]):
    """One session for both calls — resolve_ingredients and apply_cap
    would otherwise each open their own Swiggy connection."""
    async with instamart_session() as session:
        lines, unresolved = await resolve_ingredients(address_id, ingredients, session=session)
    kept, dropped = apply_cap(lines)
    return kept, dropped, unresolved


def start_gap_order(user_id: int, address_id: str, ingredients: list[str]) -> dict:
    """Builds and stages a cart. Never checks out — confirm_gap_order() is
    the only function allowed to do that (prompts.py rule 4)."""
    kept, dropped, unresolved = run(lambda: _resolve_and_cap(address_id, ingredients))
    state = get_or_create_state(user_id)
    state.pending_order = PendingOrder(kept=kept, dropped=dropped, address_id=address_id)
    return {
        "kept": [_line_dict(l) for l in kept],
        "dropped": [_line_dict(l) for l in dropped],
        "unresolved": [{"ingredient": u.ingredient, "reason": u.reason} for u in unresolved],
        "total": cart_total(kept),
    }


def confirm_gap_order(user_id: int) -> dict:
    """Places the real, COD order. Refuses if there's no staged cart —
    guards against being called without a start_gap_order earlier this
    conversation."""
    state = get_or_create_state(user_id)
    pending = state.pending_order
    if pending is None:
        return {"error": "no cart to confirm — call start_gap_order first"}

    mark_address_confirmed(user_id)
    summary = run(lambda: place_order(user_id, pending.address_id, pending.kept, pending.dropped))
    state.pending_order = None
    return {
        "order_id": summary.order_id,
        "total": summary.total,
        "dropped_for_cap": [l.name for l in summary.dropped_for_cap],
    }


def record_item_correction(user_id: int, canonical_name: str, direction: str) -> dict:
    new_m = record_correction(user_id, canonical_name, direction)
    if new_m is None:
        return {"error": f"{canonical_name!r} is not in the pantry — nothing to correct"}
    return {"canonical_name": canonical_name, "new_pace_multiplier": round(new_m, 2)}


# --- LLM-facing registry ---------------------------------------------------
# user_id is deliberately absent from every schema below: dispatch() is the
# only place model-supplied args and the session's user_id meet.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "onboard_user",
            "description": "Create or update the household's profile: how many people, and their diet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "household_size": {"type": "integer", "description": "Number of people in the household"},
                    "diet": {"type": "string", "enum": ["vegan", "veg", "egg", "non_veg"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_addresses",
            "description": "List the household's saved Swiggy delivery addresses. Always call this before building a gap order, even if one was picked earlier in this conversation.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_orders",
            "description": "Pull recent Instamart order history and update the inferred pantry from it.",
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer", "description": "How many recent orders to pull"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pantry_status",
            "description": "The household's current pantry: each item's name, confidence (0-1, never a certainty), and bucket (likely/maybe/out).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_recipes",
            "description": "Rank recipes by what the household already owns, filtered to their diet.",
            "parameters": {
                "type": "object",
                "properties": {"top_n": {"type": "integer", "description": "How many recipes to return"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_gap_order",
            "description": (
                "Search for and price the given ingredients against one delivery address, apply the "
                "₹1000 cap, and stage a cart. Does NOT place the order — always show the result to the "
                "household and wait for an explicit yes, in its own message, before calling confirm_gap_order."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address_id": {"type": "string", "description": "The address id the household just picked from list_addresses"},
                    "ingredients": {"type": "array", "items": {"type": "string"}, "description": "Canonical ingredient names to shop for"},
                },
                "required": ["address_id", "ingredients"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_gap_order",
            "description": (
                "Place the staged cart as a real, cash-on-delivery order. Only call this after the "
                "household has explicitly said yes to the cart start_gap_order returned, in a separate message."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_item_correction",
            "description": "Record that an item ran out earlier than expected, or lasted longer than expected, to tune future pantry estimates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "canonical_name": {"type": "string"},
                    "direction": {"type": "string", "enum": ["ran_out_early", "lasted_longer"]},
                },
                "required": ["canonical_name", "direction"],
            },
        },
    },
]

TOOLS = {
    "onboard_user": onboard_user,
    "list_addresses": list_addresses,
    "sync_orders": sync_orders,
    "get_pantry_status": get_pantry_status,
    "suggest_recipes": suggest_recipes,
    "start_gap_order": start_gap_order,
    "confirm_gap_order": confirm_gap_order,
    "record_item_correction": record_item_correction,
}


def dispatch(name: str, args: dict, user_id: int):
    if name not in TOOLS:
        return {"error": f"unknown tool {name!r}"}
    return TOOLS[name](user_id=user_id, **args)
