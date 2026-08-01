"""Core IP: consumption-decay math + confidence scoring.

Given purchase events for a canonical ingredient, estimates the probability
it is still in the kitchen (exponential decay per category, scaled by
household size). Output is always a confidence, never an assertion.
"""

from swiggy_buzz.pantry_engine.confidence import (
    bucket,
    item_bucket,
    item_confidence,
    usable_life_days,
)
from swiggy_buzz.pantry_engine.corrections import (
    apply_correction,
    next_m,
    record_correction,
)

__all__ = [
    "item_confidence",
    "usable_life_days",
    "bucket",
    "item_bucket",
    "apply_correction",
    "next_m",
    "record_correction",
]
