"""Core confidence math (MATH.md §2, §6). Pure functions only — no DB access,
no datetime.now(). `now` is always a parameter so the golden vectors in §8 are
deterministic. Timestamps are UTC ISO-8601.
"""

import logging
import math
from datetime import datetime

from swiggy_buzz.config import DEFAULT_DECAY_DAYS
from swiggy_buzz.pantry_engine.constants import (
    HOUSEHOLD_EXP,
    LIKELY_AT,
    LN20,
    MAYBE_AT,
    SHAPE_K,
    SHELF_LIFE_DAYS,
    U_MIN_DAYS,
    UNKNOWN_CATEGORY_DECAY_DAYS,
)
from swiggy_buzz.store.models import PantryItem

logger = logging.getLogger(__name__)


def usable_life_days(category: str, household_size: int) -> float:
    """U = min(S, D·Q/H), floored at U_MIN_DAYS (§3).

    Quantity may never stretch life past shelf life (the min); user corrections
    can (m applies later, in item_confidence). Unknown category → D=21, S=None,
    logged — never raises (§4).
    """
    if category in DEFAULT_DECAY_DAYS:
        d = DEFAULT_DECAY_DAYS[category]
        s = SHELF_LIFE_DAYS.get(category)
    else:
        logger.warning("unknown pantry category %r; falling back to D=%d, S=None",
                       category, UNKNOWN_CATEGORY_DECAY_DAYS)
        d = UNKNOWN_CATEGORY_DECAY_DAYS
        s = None

    q = 1.0  # v2: item.purchase_qty / REF_QTY[category]
    h = household_size ** HOUSEHOLD_EXP
    consumption_days = d * q / h
    u = min(s, consumption_days) if s is not None else consumption_days
    return max(u, U_MIN_DAYS)


def item_confidence(item: PantryItem, household_size: int, now: datetime) -> float:
    """C(t) = exp(−ln20 · x²), x = m·t/U (§2). Probability the item is still
    usable. C(0)=1 exactly; C=0.05 at end of expected life."""
    elapsed = (now - datetime.fromisoformat(item.last_purchased_at)).total_seconds() / 86400
    t = max(0.0, elapsed)  # future timestamp (clock skew) ⇒ just bought
    m = item.decay_lambda if item.decay_lambda is not None else 1.0
    u = usable_life_days(item.category, household_size)
    x = m * t / u
    return math.exp(-LN20 * x ** SHAPE_K)


def bucket(confidence: float) -> str:
    """Confidence → shelf semantics (§9): 'likely' | 'maybe' | 'out'."""
    if confidence >= LIKELY_AT:
        return "likely"
    if confidence >= MAYBE_AT:
        return "maybe"
    return "out"
