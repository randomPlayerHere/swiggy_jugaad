"""Core confidence math (MATH.md §2, §6). Pure functions only — no DB access,
no datetime.now(). `now` is always a parameter so the golden vectors in §8 are
deterministic. Timestamps are UTC ISO-8601; naive datetimes (no tzinfo) are
assumed UTC so a stored-vs-caller convention mismatch can't crash the scan.
"""

import logging
import math
from datetime import datetime, timezone

from swiggy_jugaad.config import DEFAULT_DECAY_DAYS
from swiggy_jugaad.pantry_engine.constants import (
    HOUSEHOLD_EXP,
    LIKELY_AT,
    LN20,
    MAYBE_AT,
    SHAPE_K,
    SHELF_LIFE_DAYS,
    U_MIN_DAYS,
    UNKNOWN_CATEGORY_DECAY_DAYS,
)
from swiggy_jugaad.store.models import PantryItem

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Attach UTC to a naive datetime; leave aware ones untouched (§6). Lets
    naive and aware timestamps be subtracted without a TypeError."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


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
    h = max(1, household_size) ** HOUSEHOLD_EXP  # guard 0/negative → treat as 1
    consumption_days = d * q / h
    u = min(s, consumption_days) if s is not None else consumption_days
    return max(u, U_MIN_DAYS)


def age_days(item: PantryItem, now: datetime) -> float:
    """t in §2: days since last purchase, never negative (a future timestamp
    from clock skew reads as just bought)."""
    purchased = _as_utc(datetime.fromisoformat(item.last_purchased_at))
    elapsed = (_as_utc(now) - purchased).total_seconds() / 86400
    return max(0.0, elapsed)


def item_confidence(item: PantryItem, household_size: int, now: datetime) -> float:
    """C(t) = exp(−ln20 · x²), x = m·t/U (§2). Probability the item is still
    usable. C(0)=1 exactly; C=0.05 at end of expected life."""
    t = age_days(item, now)
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


def item_bucket(item: PantryItem, household_size: int, now: datetime) -> str:
    """Shelf semantics for an item (§9), with is_out as a hard override: a
    household that reported ran_out_early reads 'out' regardless of the curve.
    Use this rather than bucket(item_confidence(...)) so the flag is honored."""
    if item.is_out:
        return "out"
    return bucket(item_confidence(item, household_size, now))
