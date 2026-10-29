# %%
# Regenerates the README confidence-decay chart straight from the production
# math (swiggy_jugaad.pantry_engine.confidence) — nothing here is hand-copied
# from MATH.md, so the chart can't drift from what the app actually computes.
# Run with `uv run scripts/decay_chart.py`. Edit CURVES and re-run for
# what-ifs (e.g. add an eggs or spices line).

from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np

from swiggy_jugaad.pantry_engine.confidence import item_confidence
from swiggy_jugaad.store.models import PantryItem

PURCHASED = datetime(2026, 1, 1)
DAYS = np.linspace(0, 30, 200)

# %%
def curve(category: str, household_size: int) -> np.ndarray:
    item = PantryItem(
        id=0, user_id=0, canonical_name=category, category=category,
        last_purchased_at=PURCHASED.isoformat(),
        purchase_qty=None, decay_lambda=None, is_out=False,
    )
    return np.array([
        item_confidence(item, household_size, PURCHASED + timedelta(days=float(d)))
        for d in DAYS
    ])


# Worked examples A & B from pantry_engine/MATH.md — same categories, same
# math, household size alone separates the two rice lines. `label_day` picks
# where each label anchors along its own curve, hand-spaced so the three
# don't collide (they'd otherwise all converge near C=0 by day 15-20).
CURVES = [
    ("milk · household of 1", "dairy", 1, "#2a78d6", 2.2),
    ("rice · household of 4", "rice_grains", 4, "#1baf7a", 6.0),
    ("rice · household of 1", "rice_grains", 1, "#eb6834", 13.5),
]

# %%
fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)

for label, category, household, color, label_day in CURVES:
    y = curve(category, household)
    ax.plot(DAYS, y, color=color, linewidth=2.5, solid_capstyle="round")
    idx = int(np.argmin(np.abs(DAYS - label_day)))
    ax.annotate(
        label, xy=(DAYS[idx], y[idx]), xytext=(0, 14), textcoords="offset points",
        ha="center", color=color, fontsize=11, fontweight="bold", clip_on=False,
    )

for level, tag in [(0.7, "likely"), (0.3, "maybe / out")]:
    ax.axhline(level, color="#8a8a86", linewidth=1, linestyle="--", alpha=0.6, zorder=0)
    ax.text(0.4, level + 0.015, f"{tag}  ({level:.0%})", color="#6b6a66", fontsize=9, va="bottom")

ax.set_xlim(0, 30)
ax.set_ylim(0, 1.05)
ax.set_xlabel("days since last purchase")
ax.set_ylabel("confidence  C(t)")
ax.set_title("Not a fuel gauge — a belief that decays\nsame purchase, same category, household size alone splits the curves")
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(colors="#52514e")
fig.tight_layout()
fig.savefig("docs/decay_chart.png", facecolor="white", bbox_inches="tight")
print("saved docs/decay_chart.png")
# No plt.show(): `uv run scripts/decay_chart.py` is headless and it'd hang
# waiting for a GUI backend. Running cell-by-cell in a Jupyter/VS Code
# interactive window still displays the figure inline after this cell.
