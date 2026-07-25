# Pantry Engine — Math Specification (source of truth)

Status: agreed 2026-07-12. Implementation and tests must match this document;
if the code and this file disagree, this file wins until explicitly amended.

## 1. What the number means

For every pantry item we output a **confidence** `C ∈ (0, 1]`: the probability
the item is still *usable* in the kitchen. It is never an assertion
("Rice 91%", never "You have rice"). An item stops being usable through
whichever happens first:

- **consumption** — the household finished it (depends on household size,
  pack quantity, habits), or
- **spoilage** — it went off (depends only on shelf life; 1 L of milk sours
  on the same day as 2 L).

**C is a belief, not a fuel gauge.** The engine's only observables are
purchase events and user answers — it cannot see cooking. So "rice 84% at
day 5" means "households like this one still have rice 84% of the time by
day 5," NOT "16% of the pack is gone." An untouched pack reading < 100% is
correct behavior, not a bug: the D values already average over idle days,
the ≥ 0.7 bucket makes early drift behaviorally identical to 100%, and
households that let items sit get learned via `lasted_longer` → lower m.
Tracking actual usage requires event-based deduction ("cooked it", §10) —
deliberately v2.

## 2. The master formula

```
C(t) = exp( −ln(20) · x² )          equivalently  C(t) = 0.05 ^ (x²)

where x = m · t / U                 "personalized fraction of life used"

  t = days since last purchase                  (float, ≥ 0)
  U = usable life in days = min(S, D·Q/H)       (the two clocks)
  m = personal pace multiplier                  (learned; default 1.0)
```

Components of `U`:

| symbol | meaning | value |
|--------|---------|-------|
| `D` | days a **typical pack** lasts a **1-person** household (consumption prior) | `config.DEFAULT_DECAY_DAYS[category]` |
| `H` | household factor | `household_size ** 0.7` |
| `Q` | quantity factor | **v1: hard-coded 1.0.** v2: `purchase_qty / REF_QTY[category]` |
| `S` | shelf life cap (spoilage clock) | `SHELF_LIFE_DAYS[category]`; `None` = no cap |

Properties that make this the right curve:

- `C(0) = 1.0` exactly — just bought ⇒ certainly there.
- `C = 0.05` exactly when `x = 1` — "depleted" is defined as 5 % confidence,
  never 0 (matches the "never assert" convention).
- The **x² (squared) exponent** is deliberate. Plain exponential
  (`exp(−ln20·x)`) is memoryless: it claims milk bought *yesterday* is at
  47 %, which is obviously wrong and would train users to distrust the bot.
  With x², hazard grows linearly with age: fresh items barely decay, aging
  items decay fast. (Formally: Weibull survival, shape k = 2. CLAUDE.MD's
  "exponential decay" is this — a stretched exponential.)

Human-readable consequence (with the bucket thresholds below): every item is
**"likely" for the first ~34.5 % of its life, "maybe" until ~63.4 %, then
"probably out."**

## 3. The two clocks, and who may override whom

```
consumption_days = D · Q / H        scaled by household and quantity
U = min(S, consumption_days)        spoilage caps consumption
life = U / m                        user corrections rescale everything
```

Precedence rule: **quantity can never stretch life past shelf life
(the `min`), but user corrections can (m applies after the min).**
Rationale: quantity is an inference; a correction is a direct observation
(e.g. the household buys UHT milk that keeps 10 days — believe them).

## 4. Constants

```python
DEPLETED_AT   = 0.05          # C at end of expected life; LN20 = ln(1/0.05)
SHAPE_K       = 2             # exponent on x (do not make configurable)
HOUSEHOLD_EXP = 0.7           # sublinear: 2 people ≈ 1.62×, 4 ≈ 2.64×
M_UP, M_DOWN  = 1.2, 0.8      # correction steps (ran_out_early / lasted_longer)
M_MIN, M_MAX  = 0.2, 5.0      # clamp on m  (life adjustable 5× either way)
U_MIN_DAYS    = 0.5           # floor on U (guards divide-by-tiny)
LIKELY_AT     = 0.7           # C ≥ 0.7  → "likely"
MAYBE_AT      = 0.3           # 0.3–0.7  → "maybe";  < 0.3 → "out"
```

Household factor table (`H = size^0.7`):
1 → 1.000 · 2 → 1.625 · 3 → 2.158 · 4 → 2.639 · 5 → 3.085 · 6 → 3.505

`SHELF_LIFE_DAYS` (spoilage cap; `None` = effectively infinite):

| category | D (config) | S |
|---|---|---|
| dairy | 4 | 5 |
| produce | 5 | 6 |
| bread | 4 | 5 |
| eggs | 10 | 21 |
| snacks | 7 | 45 |
| rice_grains | 21 | None |
| pulses | 30 | None |
| oil | 45 | None |
| spices | 90 | None |

Note: in v1 (Q = 1) the shelf cap never binds because D ≤ S everywhere. It
exists to future-proof v2 quantity (2 L milk must not "last 8 days") and it
documents the physics. Keep it.

Unknown category (LLM ingester emits something new): fall back to
`D = 21, S = None` and log a warning — never raise.

## 5. Personalization: the m multiplier and corrections

`m` is a dimensionless **pace multiplier** stored per (user, item) in the
`pantry_items.decay_lambda` column. `NULL` means `m = 1.0`. Higher m = the
household depletes this item faster than the prior; effective life = `U / m`.

On a correction:

```
ran_out_early : m ← clamp(m · 1.2, 0.2, 5.0)     # they consume faster
lasted_longer : m ← clamp(m · 0.8, 0.2, 5.0)     # they consume slower
```

Both update `decay_lambda` via `update_decay_lambda()` AND log the row via
`add_correction()`. Additional immediate effects:

- `lasted_longer`: nothing else needed — lowering m instantly raises today's
  C (the user just told us it's still there, and the math now agrees more).
- `ran_out_early`: tuning m only fixes the *future*; the item is out *now*.
  The **bot layer** must additionally mark the item out (`is_out = 1`, via
  `mark_item_out()`) so it drops to "out" immediately and becomes a gap-order
  candidate. The row — and its learned `m` — is **kept**, not deleted:
  deleting would discard the very lesson `ran_out_early` just taught (see the
  repurchase rule below). `delete_pantry_item()` is reserved for a genuine
  "remove this item" action, not for corrections.

Why m (a multiplier) and not a stored absolute rate: household size changes,
v2 quantity, and category re-classification all flow through automatically;
m only carries the *learned deviation from the prior*, which survives all of
them.

`m` is preserved on repurchase (it is a household trait, not a pack trait).
A repurchase resets `last_purchased_at` and clears `is_out` (and, v2,
`purchase_qty`); `decay_lambda` (m) is left untouched, so a household that
kept running out early re-enters already knowing "you use this fast."
Overlapping leftovers from a previous pack are deliberately ignored.

## 6. Reference pipeline (implementation must match)

```python
LN20 = math.log(20)

def item_confidence(item, household_size, now) -> float:
    t = max(0.0, (now - parse(item.last_purchased_at)).total_seconds() / 86400)
    H = household_size ** 0.7
    Q = 1.0                       # v2: item.purchase_qty / REF_QTY[item.category]
    D = DEFAULT_DECAY_DAYS.get(item.category, 21)
    S = SHELF_LIFE_DAYS.get(item.category)
    U = max(min(S, D * Q / H) if S is not None else D * Q / H, 0.5)
    m = item.decay_lambda if item.decay_lambda is not None else 1.0
    x = m * t / U
    return math.exp(-LN20 * x * x)
```

Timestamps are UTC ISO-8601; `t` is fractional days; `now` is always a
parameter (never `datetime.now()` inside the math) so tests are deterministic.

## 7. Worked examples

**A. Priya, lives alone (H=1), buys milk** (D=4, S=5 → U=4):

| day | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| C | 1.00 | 0.83 | 0.47 | 0.19 | 0.05 | 0.01 |

Day 1 the bot says "milk 83 %"; day 2 it's in the ask-band ("still have
milk?"); by day 4 it's a gap-order candidate. Her rice (U=21) meanwhile:
day 3 → 94 %, day 7 → 72 %, day 10 → 51 %, day 14 → 26 %.

**B. The Sharmas, family of 4 (H=2.639), same rice** (U = 21/2.639 ≈ 7.96 d):
day 2 → 83 %, day 3 → 65 %, day 5 → 31 %, day 8 → 5 %. Same purchase, same
category — household scaling alone separates the two households.

**C. Corrections converge (and where they hit their limit).** The Sharmas
actually buy 5 kg bags; true life ≈ 21·5/2.639 ≈ **39.8 days**, but v1
(Q=1) predicts 7.96. Each time the bot wrongly proposes rice, the user says
"still have it" → `lasted_longer` → m ×0.8: predicted life goes
7.96 → 9.95 → 12.4 → 15.5 → 19.4 → 24.3 → 30.4 → 38.0 → clamp at m=0.2 →
**39.8 days — exactly the truth**. Eight corrections; a 10 kg bag would
exceed the 5× clamp and v1 could never fully learn it. v2 quantity
(Q=5 from the pack size) gets there in **one step** with zero corrections —
that's the v2 payoff, stated precisely.

**D. Spoilage cap (v2 preview).** Priya buys 2 L milk (Q=2):
consumption clock = 8 d, but U = min(5, 8) = **5 d** — quantity cannot beat
souring. If she then reports `lasted_longer` (UHT milk), m=0.8 → life 6.25 d:
corrections *can* beat the shelf prior, by design (§3).

**E. Repurchase.** Milk at day 3 (19 %); a new Instamart order containing
milk resets `last_purchased_at` → C jumps to 100 %; m unchanged.

## 8. Golden test vectors (assert to 3 decimals)

| case | D | S | household | m | t (days) | expected C |
|---|---|---|---|---|---|---|
| milk | 4 | 5 | 1 | 1.0 | 1 | 0.829 |
| milk | 4 | 5 | 1 | 1.0 | 2 | 0.473 |
| rice | 21 | – | 1 | 1.0 | 7 | 0.717 |
| rice | 21 | – | 4 | 1.0 | 4 | 0.469 |
| rice | 21 | – | 4 | 0.8 | 4 | 0.616 |
| spices | 90 | – | 2 | 1.0 | 30 | 0.415 |
| eggs | 10 | 21 | 2 | 1.0 | 3 | 0.491 |
| anything | any | any | any | any | 0 | 1.000 |

Plus property tests: C monotonically decreasing in t; C(t=0)=1 always;
C = 0.05 at t = U/m (S=None case); household 4 < household 1 at equal t;
m clamps stop at [0.2, 5.0]; unknown category behaves as D=21.

## 9. Bucket semantics and the flywheel

```
C ≥ 0.7        "likely have"   → recipe ranker counts it as owned
0.3 ≤ C < 0.7  "maybe"         → bot asks; the answer IS a correction
C < 0.3        "probably out"  → gap-order candidate
```

`is_out = 1` is a **hard override**: the item reads "out" regardless of the
curve (the household told us directly). The bucket is computed on the item, not
the bare confidence — see `item_bucket()`.

The ask-band is the calibration engine: every "still have rice?" answer
tunes m, so a household's questions get rarer as its model gets sharper.

## 10. v2 hooks (designed for, not built)

- `REF_QTY[category]` — typical pack the D values assume, e.g. dairy 0.5 L,
  rice_grains 1 kg, eggs 6, oil 1 L, pulses 500 g, produce 500 g, bread
  1 loaf, spices 100 g, snacks 1 pack. Requires the ingester to normalize
  units ("2 × 500 ml" → 1.0 L). Then `Q = purchase_qty / REF_QTY`.
- "Cooked it" deduction and quantity draw-down: out of scope; the model
  stays purchase-event-driven. This is the true fix for the "bought rice
  5 days ago but never cooked it" gap: usage events would advance the
  consumed fraction directly (event-driven), with time decay left to cover
  background drift and spoilage only. Until then, m absorbs chronic
  intermittent use and the maybe-band question catches acute cases.
