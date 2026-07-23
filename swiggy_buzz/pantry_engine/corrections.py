"""Personalization: nudge the pace multiplier m from user answers (MATH.md §5).

ran_out_early → m ×1.2 (consume faster); lasted_longer → m ×0.8 (slower),
both clamped to [0.2, 5.0]. This module tunes and persists m only. It does NOT
delete the item on ran_out_early — that is the bot layer's job (it calls
repo.delete_pantry_item() so the item drops to 'out' immediately).
"""

from swiggy_buzz.pantry_engine.constants import M_DOWN, M_MAX, M_MIN, M_UP
from swiggy_buzz.store import repo

RAN_OUT_EARLY = "ran_out_early"
LASTED_LONGER = "lasted_longer"

_STEP = {RAN_OUT_EARLY: M_UP, LASTED_LONGER: M_DOWN}


def _clamp(m: float) -> float:
    return max(M_MIN, min(M_MAX, m))


def next_m(current_m: float | None, direction: str) -> float:
    """Pure: the new multiplier after one correction. NULL/None ⇒ m=1.0."""
    if direction not in _STEP:
        raise ValueError(f"unknown correction direction: {direction!r}")
    m = current_m if current_m is not None else 1.0
    return _clamp(m * _STEP[direction])


def apply_correction(
    user_id: int, canonical_name: str, direction: str, current_m: float | None
) -> float:
    """Compute the new m, persist it, and log the correction row. Returns the
    new m. Caller is responsible for deleting the item on ran_out_early (§5)."""
    m = next_m(current_m, direction)
    repo.update_decay_lambda(user_id, canonical_name, m)
    repo.add_correction(user_id, canonical_name, direction)
    return m
