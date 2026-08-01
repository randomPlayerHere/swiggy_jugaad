"""Personalization: nudge the pace multiplier m from user answers (MATH.md §5).

ran_out_early → m ×1.2 (consume faster); lasted_longer → m ×0.8 (slower),
both clamped to [0.2, 5.0]. The bot's one-call entry point is
record_correction(): it looks up the item, tunes and persists m, logs the row,
and on ran_out_early also marks the item out (is_out=1) so it drops to 'out'
now — the row and its learned m are kept for the next repurchase (§5).
apply_correction() is the lower-level primitive: it only tunes m (the caller
supplies current_m and, for ran_out_early, must mark the item out itself).
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
    new m. Caller is responsible for marking the item out on ran_out_early via
    repo.mark_item_out() (§5) — the row and its m are kept, not deleted."""
    m = next_m(current_m, direction)
    repo.update_decay_lambda(user_id, canonical_name, m)
    repo.add_correction(user_id, canonical_name, direction)
    return m


def record_correction(
    user_id: int, canonical_name: str, direction: str
) -> float | None:
    """One-call correction for the bot: looks up the item's current m, applies
    the correction (tunes m, persists it, logs the row), and on ran_out_early
    also marks the item out (is_out=1) so it drops to 'out' now while keeping
    the row and its learned m for the next repurchase (§5). Returns the new m,
    or None if the item isn't in the pantry (nothing to correct)."""
    item = repo.get_pantry_item(user_id, canonical_name)
    if item is None:
        return None
    m = apply_correction(user_id, canonical_name, direction, item.decay_lambda)
    if direction == RAN_OUT_EARLY:
        repo.mark_item_out(user_id, canonical_name)
    return m
