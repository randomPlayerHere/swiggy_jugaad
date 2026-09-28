"""Pantry-engine math constants. Values are fixed by pantry_engine/MATH.md §4 —
amend the spec before changing anything here. Consumption priors (D) live in
config.DEFAULT_DECAY_DAYS; this module owns everything else.
"""

import math

# --- Depletion definition ---
DEPLETED_AT = 0.05            # C at end of expected life; never asserts 0
LN20 = math.log(1 / DEPLETED_AT)

# --- Curve shape ---
SHAPE_K = 2                   # x² hazard (Weibull k=2); do not make configurable

# --- Household scaling ---
HOUSEHOLD_EXP = 0.7           # H = household_size ** 0.7 (sublinear)

# --- Personal pace multiplier m (stored in pantry_items.decay_lambda) ---
M_UP = 1.2                    # ran_out_early: they consume faster
M_DOWN = 0.8                  # lasted_longer: they consume slower
M_MIN = 0.2                   # clamp: life adjustable at most 5x either way
M_MAX = 5.0

# --- Guards ---
U_MIN_DAYS = 0.5              # floor on usable life; guards divide-by-tiny

# --- Bucket thresholds (§9) ---
LIKELY_AT = 0.7               # C >= 0.7        -> "likely have"
MAYBE_AT = 0.3                # 0.3 <= C < 0.7  -> "maybe" (ask-band); < 0.3 -> "out"

# --- Fallback for categories the LLM ingester invents (§4) ---
UNKNOWN_CATEGORY_DECAY_DAYS = 21

# --- Spoilage caps in days; None = no cap (§4) ---
# In v1 (Q=1) these never bind because D <= S everywhere; kept to future-proof
# v2 quantity (2 L milk must not "last 8 days") and to document the physics.
SHELF_LIFE_DAYS = {
    "dairy": 5,
    "produce": 6,
    "bread": 5,
    "eggs": 21,
    "snacks": 45,
    "rice_grains": None,
    "pulses": None,
    "oil": None,
    "spices": None,
}
