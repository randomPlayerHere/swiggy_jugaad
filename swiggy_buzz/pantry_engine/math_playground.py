# =============================================================================
# Pantry Engine — MATH.md playground
# Copy each "# %% [cell N]" block into its own Jupyter cell, top to bottom.
# Self-contained: no project imports, so the kernel needs no sys.path setup.
# Everything mirrors pantry_engine/MATH.md; if you change a constant here you
# are experimenting, not amending the spec.
# =============================================================================

# %% [cell 1] — setup: constants + the master formula
import math

import matplotlib.pyplot as plt
import numpy as np

# --- constants (MATH.md §4) ---
DEPLETED_AT = 0.05
LN20 = math.log(1 / DEPLETED_AT)
SHAPE_K = 2
HOUSEHOLD_EXP = 0.7
M_UP, M_DOWN = 1.2, 0.8
M_MIN, M_MAX = 0.2, 5.0
U_MIN_DAYS = 0.5
LIKELY_AT, MAYBE_AT = 0.7, 0.3
UNKNOWN_D = 21

DEFAULT_DECAY_DAYS = {
    "dairy": 4, "produce": 5, "bread": 4, "eggs": 10, "rice_grains": 21,
    "pulses": 30, "oil": 45, "spices": 90, "snacks": 7,
}
SHELF_LIFE_DAYS = {
    "dairy": 5, "produce": 6, "bread": 5, "eggs": 21, "snacks": 45,
    "rice_grains": None, "pulses": None, "oil": None, "spices": None,
}

# --- the math (MATH.md §2, §6) ---
def usable_life(category, household_size, Q=1.0):
    D = DEFAULT_DECAY_DAYS.get(category, UNKNOWN_D)
    S = SHELF_LIFE_DAYS.get(category)
    H = household_size ** HOUSEHOLD_EXP
    consumption = D * Q / H
    U = min(S, consumption) if S is not None else consumption
    return max(U, U_MIN_DAYS)

def confidence(t, category, household_size=1, m=1.0, Q=1.0, k=SHAPE_K):
    """C(t) = exp(-ln20 * x**k), x = m*t/U.  k exposed only for experiments."""
    U = usable_life(category, household_size, Q)
    x = m * max(t, 0.0) / U
    return math.exp(-LN20 * x ** k)

conf_vec = np.vectorize(confidence)

def bucket(c):
    return "likely" if c >= LIKELY_AT else ("maybe" if c >= MAYBE_AT else "out")

# --- plotting defaults (fixed categorical order; grid recessive) ---
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
           "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
plt.rcParams.update({
    "axes.prop_cycle": plt.cycler(color=PALETTE),
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.figsize": (9, 4.5), "lines.linewidth": 2,
})

def shade_buckets(ax):
    """Background bands for likely / maybe / out on a confidence axis."""
    ax.axhspan(LIKELY_AT, 1.0, color="#1baf7a", alpha=0.06)
    ax.axhspan(MAYBE_AT, LIKELY_AT, color="#eda100", alpha=0.08)
    ax.axhspan(0.0, MAYBE_AT, color="#e34948", alpha=0.06)
    ax.axhline(LIKELY_AT, color="#999", lw=0.8, ls="--")
    ax.axhline(MAYBE_AT, color="#999", lw=0.8, ls="--")
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("confidence C")

print("setup ok — e.g. milk day 1:", round(confidence(1, "dairy"), 3))


# %% [cell 2] — golden test vectors (MATH.md §8): must all pass to 3 decimals
GOLDEN = [
    # (category, household, m, t, expected)
    ("dairy",       1, 1.0,  1, 0.829),
    ("dairy",       1, 1.0,  2, 0.473),
    ("rice_grains", 1, 1.0,  7, 0.717),
    ("rice_grains", 4, 1.0,  4, 0.469),
    ("rice_grains", 4, 0.8,  4, 0.616),
    ("spices",      2, 1.0, 30, 0.415),
    ("eggs",        2, 1.0,  3, 0.491),
    ("oil",         3, 1.0,  0, 1.000),
]
print(f"{'case':<22}{'t':>4}{'expected':>10}{'got':>8}   ok")
for cat, hh, m, t, want in GOLDEN:
    got = confidence(t, cat, hh, m)
    ok = round(got, 3) == want
    print(f"{cat + f' H={hh} m={m}':<22}{t:>4}{want:>10.3f}{got:>8.3f}   {'PASS' if ok else 'FAIL <-- check!'}")


# %% [cell 3] — decay curves, single household (Priya, H=1)
# Split perishables vs staples: one shared x-axis would squash dairy into a wall.
perishables = ["dairy", "produce", "bread", "snacks", "eggs"]
staples = ["rice_grains", "pulses", "oil", "spices"]

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
for ax, cats, horizon, title in [
    (axes[0], perishables, 14, "Perishables (H=1)"),
    (axes[1], staples, 120, "Staples (H=1)"),
]:
    t = np.linspace(0, horizon, 400)
    for i, cat in enumerate(cats):
        c = conf_vec(t, cat)
        (line,) = ax.plot(t, c)
        # direct label on the curve, staggered heights so labels never collide
        c_label = 0.88 - 0.13 * i
        U = usable_life(cat, 1)
        t_label = U * math.sqrt(math.log(1 / c_label) / LN20)
        ax.annotate(cat, (min(t_label, horizon * 0.98), c_label), xytext=(5, 3),
                    textcoords="offset points", color=line.get_color(), fontsize=9)
    shade_buckets(ax)
    ax.set_xlim(0, horizon)
    ax.set_xlabel("days since purchase")
    ax.set_title(title, fontsize=11)
fig.suptitle("Green band = likely, amber = ask-band, red = gap-order candidate", fontsize=9, y=1.02)
plt.tight_layout()
plt.show()


# %% [cell 4] — household scaling: same rice purchase, households 1–6
fig, ax = plt.subplots()
t = np.linspace(0, 25, 400)
for size in range(1, 7):
    c = conf_vec(t, "rice_grains", size)
    (line,) = ax.plot(t, c)
    c_label = 0.9 - 0.12 * (6 - size)
    U = usable_life("rice_grains", size)
    t_label = U * math.sqrt(math.log(1 / c_label) / LN20)
    ax.annotate(f"H={size}", (t_label, c_label), xytext=(5, 3),
                textcoords="offset points", color=line.get_color(), fontsize=9)
shade_buckets(ax)
ax.set_xlim(0, 25)
ax.set_xlabel("days since purchase")
ax.set_title("Rice, 1 kg: household size alone separates the curves (H = size^0.7)", fontsize=11)
plt.show()

print("effective rice life U (days) by household size:")
for size in range(1, 7):
    print(f"  {size} person(s): {usable_life('rice_grains', size):5.2f}")


# %% [cell 5] — WHY x² and not plain exponential (the k=1 strawman, §2)
# k=1 is memoryless: milk bought YESTERDAY would read 47%. k=2 keeps fresh
# items near 1.0 and lets aging items fall fast. Try k=3 too — is it better
# or does it hold "certain" implausibly long then cliff-dive?
fig, ax = plt.subplots()
t = np.linspace(0, 6, 300)
for k, style in [(1, "--"), (2, "-"), (3, ":")]:
    c = conf_vec(t, "dairy", k=k)
    ax.plot(t, c, style, color=PALETTE[0] if k == 2 else "#888",
            label=f"k={k}" + ("  (spec)" if k == 2 else ""))
shade_buckets(ax)
ax.set_xlim(0, 6)
ax.set_xlabel("days since purchase (milk, H=1, U=4)")
ax.legend()
ax.set_title("Shape exponent k: k=1 says day-1 milk is 47% — users would revolt", fontsize=11)
plt.show()

for k in (1, 2, 3):
    print(f"k={k}: milk day 1 -> {confidence(1, 'dairy', k=k):.2f},  day 3 -> {confidence(3, 'dairy', k=k):.2f}")


# %% [cell 6] — bucket geometry: life-fractions are UNIVERSAL (category-free)
# x at a threshold c is sqrt(ln(1/c)/ln20) — no D, H, m in it. So every item
# spends the same *fraction* of its life in each bucket. Verify the §2 claim
# (~34.5% likely, ~63.4% maybe-boundary) and see what it means in real days.
x_likely = math.sqrt(math.log(1 / LIKELY_AT) / LN20)
x_maybe = math.sqrt(math.log(1 / MAYBE_AT) / LN20)
print(f"likely until x = {x_likely:.3f} of life;  ask-band until x = {x_maybe:.3f}")
print(f"ask-band width  = {x_maybe - x_likely:.3f} of life (the calibration window)\n")

print(f"{'category':<14}{'U (H=1)':>8}{'likely for':>12}{'ask-band':>16}")
for cat in DEFAULT_DECAY_DAYS:
    U = usable_life(cat, 1)
    print(f"{cat:<14}{U:>8.1f}{x_likely * U:>10.1f} d{x_likely * U:>8.1f}–{x_maybe * U:.1f} d")

# Robustness question: is the dairy ask-band (~1.2 days wide) long enough that
# a once-a-day bot check-in actually lands inside it? If the bot polls daily,
# any band narrower than ~1 day can be skipped over entirely.


# %% [cell 7] — corrections: convergence of m (worked example C, §7)
# Sharmas (H=2.639) buy 5 kg rice: true life ~39.8 d, v1 predicts 7.96 d.
# Each wrong "out of rice?" -> lasted_longer -> m *= 0.8 (clamped at 0.2).
def apply_correction(m, kind):
    step = M_UP if kind == "ran_out_early" else M_DOWN
    return min(max(m * step, M_MIN), M_MAX)

H = 4 ** HOUSEHOLD_EXP
U_v1 = usable_life("rice_grains", 4)          # Q=1 -> 7.96 d
true_life = 21 * 5 / H                        # Q=5 ground truth -> 39.8 d

m, lives = 1.0, []
for _ in range(12):
    lives.append(U_v1 / m)
    m = apply_correction(m, "lasted_longer")

fig, ax = plt.subplots()
ax.plot(range(len(lives)), lives, "o-", color=PALETTE[0])
ax.axhline(true_life, color=PALETTE[3], ls="--")
ax.annotate(f"truth: {true_life:.1f} d (5 kg pack)", (0.3, true_life), xytext=(0, 6),
            textcoords="offset points", color=PALETTE[3], fontsize=9)
ax.axhline(U_v1 / M_MIN, color="#999", ls=":", lw=1)
ax.annotate(f"m clamp ceiling: {U_v1 / M_MIN:.1f} d", (6, U_v1 / M_MIN), xytext=(0, -14),
            textcoords="offset points", color="#777", fontsize=9)
ax.set_xlabel("number of lasted_longer corrections")
ax.set_ylabel("predicted life (days)")
ax.set_title("Eight corrections reach the truth; a 10 kg bag would exceed the 5x clamp", fontsize=11)
plt.show()

r_up, r_dn = math.log(M_UP), -math.log(M_DOWN)
print(f"corrections needed to fix a factor-r prior error:")
for r in (1.5, 2, 3, 5, 10):
    print(f"  r={r:>4}: lasted_longer x{math.log(r) / r_dn:4.1f}   ran_out_early x{math.log(r) / r_up:4.1f}"
          f"   {'<- beyond 5x clamp, v1 cannot learn it' if r > 5 else ''}")


# %% [cell 8] — robustness gotcha: alternating corrections DRIFT (not neutral!)
# ran_out_early then lasted_longer: m *= 1.2 * 0.8 = 0.96. A user who flip-flops
# doesn't return to where they started — m decays ~4% per pair. Is that
# acceptable noise-damping, or a bias? Play with M_UP/M_DOWN pairs here.
m = 1.0
trace = [m]
for i in range(30):
    m = apply_correction(m, "ran_out_early" if i % 2 == 0 else "lasted_longer")
    trace.append(m)

fig, ax = plt.subplots()
ax.plot(trace, "o-", color=PALETTE[0], markersize=4)
ax.axhline(1.0, color="#999", ls="--", lw=1)
ax.set_xlabel("alternating corrections (early, longer, early, ...)")
ax.set_ylabel("m")
ax.set_title(f"Flip-flopping user: m drifts by x{M_UP * M_DOWN} per pair — symmetric steps would need M_UP = 1/M_DOWN = 1.25", fontsize=10)
plt.show()
print(f"after 30 alternating corrections m = {trace[-1]:.3f} (started 1.0) -> life stretched x{1 / trace[-1]:.2f}")


# %% [cell 9] — property tests (§8): everything the unit tests will assert
rng = np.random.default_rng(42)
cats = list(DEFAULT_DECAY_DAYS) + ["quinoa_llm_invented"]
failures = []

def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)

print("property checks over random (category, household, m):")
for _ in range(2000):
    cat = cats[rng.integers(len(cats))]
    hh, m = int(rng.integers(1, 9)), float(rng.uniform(M_MIN, M_MAX))
    ts = np.sort(rng.uniform(0, 200, 5))
    cs = conf_vec(ts, cat, hh, m)
    if not (np.all(np.diff(cs) <= 1e-12) and 0 <= cs[-1] <= 1):
        failures.append(f"monotonicity/range broke: {cat} H={hh} m={m:.2f}")
        break
check("C monotonically decreasing, C in [0,1], 2000 random draws", not failures)
# NOTE the [0,1] not (0,1]: the spec says C is never 0, but float64 underflows
# exp() to exactly 0.0 once x > ~15.8 (i.e. ~16 lifetimes past purchase —
# dairy at day ~65 for a big household). Harmless (bucket is long since "out"),
# but it IS a spec deviation; the real confidence.py may want max(C, 1e-9).
x_underflow = math.sqrt(745 / LN20)
check(f"underflow to exactly 0.0 starts at x ~= {x_underflow:.1f} lives",
      confidence(x_underflow * 1.1 * 4, "dairy") == 0.0
      and confidence(x_underflow * 0.9 * 4, "dairy") > 0.0)
check("C(0) = 1 exactly", all(confidence(0, c, h) == 1.0 for c in cats for h in (1, 4)))
check("C = 0.05 at t = U/m (S=None case)",
      abs(confidence(usable_life("rice_grains", 3) / 0.7, "rice_grains", 3, m=0.7) - DEPLETED_AT) < 1e-9)
check("household 4 < household 1 at equal t",
      confidence(5, "rice_grains", 4) < confidence(5, "rice_grains", 1))
check("unknown category behaves as D=21",
      confidence(7, "quinoa_llm_invented", 2) == confidence(7, "rice_grains", 2))
mm = 1.0
for _ in range(50):
    mm = apply_correction(mm, "ran_out_early")
check("m clamps at M_MAX", mm == M_MAX)
mm = 1.0
for _ in range(50):
    mm = apply_correction(mm, "lasted_longer")
check("m clamps at M_MIN", mm == M_MIN)
check("U floor guards divide-by-tiny (huge household)",
      usable_life("dairy", 100) == U_MIN_DAYS)
check("shelf cap binds under v2 quantity (2 L milk capped at 5 d)",
      usable_life("dairy", 1, Q=2.0) == 5.0)
print("\nALL GREEN" if not failures else f"\n{len(failures)} FAILURES — math not robust: {failures}")


# %% [cell 10] — sensitivity: how wrong can the prior D be before buckets lie?
# If the true life differs from prior U by factor r (user's real pace), what
# does C read when the item ACTUALLY runs out (t = r*U)? And what does it read
# at half its true life? Ideally: ~likely at half-life, ~out at depletion.
fig, ax = plt.subplots()
r = np.linspace(0.4, 2.5, 300)
c_at_depletion = np.exp(-LN20 * r**2)        # x = t/U = r  when t = r*U
c_at_halflife = np.exp(-LN20 * (r / 2)**2)
ax.plot(r, c_at_halflife, color=PALETTE[0])
ax.annotate("C at true half-life (want: likely)", (1.6, float(np.exp(-LN20 * 0.64))),
            color=PALETTE[0], fontsize=9)
ax.plot(r, c_at_depletion, color=PALETTE[5])
ax.annotate("C at true depletion (want: out)", (0.55, 0.55), color=PALETTE[5], fontsize=9)
shade_buckets(ax)
ax.axvline(1.0, color="#999", lw=0.8, ls=":")
ax.set_xlabel("r = true life / prior life  (r>1: prior too pessimistic, r<1: too optimistic)")
ax.set_title("Prior can be ~30% off in either direction before buckets mislead; beyond that, m must learn", fontsize=10)
plt.show()

for r_ in (0.5, 0.7, 1.0, 1.5, 2.0):
    hl, dp = math.exp(-LN20 * (r_ / 2) ** 2), math.exp(-LN20 * r_**2)
    print(f"r={r_:.1f}: at true half-life C={hl:.2f} ({bucket(hl)}),  at true depletion C={dp:.2f} ({bucket(dp)})")


# %% [cell 11] — free play: tweak everything (uses ipywidgets if installed)
def playground(category="rice_grains", household=2, m=1.0, Q=1.0, k=2.0):
    U = usable_life(category, household, Q)
    horizon = max(2.5 * U / m, 5)
    t = np.linspace(0, horizon, 400)
    fig, ax = plt.subplots()
    ax.plot(t, conf_vec(t, category, household, m, Q, k), color=PALETTE[0])
    shade_buckets(ax)
    ax.set_xlim(0, horizon)
    ax.set_xlabel("days since purchase")
    ax.set_title(f"{category}  H={household}  m={m}  Q={Q}  k={k}   ->  U={U:.1f} d, life={U / m:.1f} d", fontsize=10)
    plt.show()
    for day in (1, 2, 3, 5, 7, 10, 14, 21, 30):
        if day <= horizon:
            c = confidence(day, category, household, m, Q, k)
            print(f"  day {day:>2}: C={c:.3f}  ({bucket(c)})")

try:
    from ipywidgets import interact, FloatSlider
    interact(playground,
             category=list(DEFAULT_DECAY_DAYS),
             household=(1, 8, 1),
             m=FloatSlider(min=M_MIN, max=M_MAX, step=0.1, value=1.0),
             Q=FloatSlider(min=0.25, max=5.0, step=0.25, value=1.0),
             k=FloatSlider(min=1.0, max=3.0, step=0.25, value=2.0))
except ImportError:
    print("ipywidgets not installed — call playground(...) by hand, e.g.:")
    playground("dairy", household=1, m=1.0, Q=2.0)
