"""Pantry-engine tests. The golden vectors and property list come straight
from MATH.md §8 (the source of truth); the rest are extra edge/robustness
cases: timezone handling, household guards, fractional days, is_out
override, and the correction round-trip through the DB.
"""

from datetime import datetime, timedelta, timezone
from functools import reduce

import pytest

from swiggy_jugaad.pantry_engine import (
    bucket,
    item_bucket,
    item_confidence,
    next_m,
    record_correction,
    usable_life_days,
)
from swiggy_jugaad.pantry_engine.confidence import LN20
from swiggy_jugaad.store.models import PantryItem, User

NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


def make_item(category, t_days, m=None, is_out=False, now=NOW):
    """A PantryItem purchased `t_days` before `now`."""
    ts = (now - timedelta(days=t_days)).isoformat()
    return PantryItem(1, 1, category, category, ts, None, m, is_out)


# --------------------------------------------------------------------------
# §8 golden vectors — assert to 3 decimals
# --------------------------------------------------------------------------

@pytest.mark.parametrize("category, t, m, household, expected", [
    ("dairy",        1, None, 1, 0.829),
    ("dairy",        2, None, 1, 0.473),
    ("rice_grains",  7, None, 1, 0.717),
    ("rice_grains",  4, None, 4, 0.469),
    ("rice_grains",  4, 0.8,  4, 0.616),
    ("spices",      30, None, 2, 0.415),
    ("eggs",         3, None, 2, 0.491),
    ("dairy",        0, None, 1, 1.000),  # anything at t=0
])
def test_golden_vectors(category, t, m, household, expected):
    assert item_confidence(make_item(category, t, m), household, NOW) == pytest.approx(expected, abs=5e-4)


# --------------------------------------------------------------------------
# §8 property tests
# --------------------------------------------------------------------------

def test_confidence_is_one_at_purchase():
    assert item_confidence(make_item("dairy", 0), 1, NOW) == 1.0


def test_monotonically_decreasing_in_time():
    seq = [item_confidence(make_item("rice_grains", t), 1, NOW) for t in range(0, 40)]
    assert all(earlier > later for earlier, later in zip(seq, seq[1:]))


@pytest.mark.parametrize("m", [1.0, 0.8, 2.0])
def test_confidence_is_depleted_at_end_of_life(m):
    # C = 0.05 exactly at t = U/m  (rice has no shelf cap)
    u = usable_life_days("rice_grains", 1)
    assert item_confidence(make_item("rice_grains", u / m, m), 1, NOW) == pytest.approx(0.05, abs=1e-9)


def test_larger_household_depletes_faster():
    assert item_confidence(make_item("rice_grains", 5), 4, NOW) < item_confidence(make_item("rice_grains", 5), 1, NOW)


def test_unknown_category_behaves_like_rice():
    assert item_confidence(make_item("caviar", 7), 1, NOW) == pytest.approx(
        item_confidence(make_item("rice_grains", 7), 1, NOW))


def test_m_clamps_at_bounds():
    assert next_m(0.2, "lasted_longer") == 0.2   # can't go below M_MIN
    assert next_m(5.0, "ran_out_early") == 5.0   # can't go above M_MAX


def test_confidence_bounded_in_unit_interval():
    # Invariant that always holds: never negative, never above 1, for any age.
    for t in (0, 0.5, 3, 21, 100, 365, 10_000):
        c = item_confidence(make_item("rice_grains", t), 3, NOW)
        assert 0.0 <= c <= 1.0


def test_confidence_strictly_positive_while_plausibly_stocked():
    # C ∈ (0, 1] holds strictly within ~1.5 lives, the range where the belief
    # is still live. Beyond that exp() underflows toward 0 (see below).
    u = usable_life_days("rice_grains", 3)
    for t in (0, u / 2, u, 1.5 * u):
        c = item_confidence(make_item("rice_grains", t), 3, NOW)
        assert 0.0 < c <= 1.0


def test_far_past_life_underflows_to_zero_but_buckets_out():
    # A forgotten item many lives overdue underflows to exactly 0.0. MATH.md §1
    # says C ∈ (0,1]; this float artifact is left unfloored since it's
    # harmless: bucket(0.0) == "out" is the correct answer anyway.
    c = item_confidence(make_item("rice_grains", 10_000), 3, NOW)
    assert c == 0.0
    assert bucket(c) == "out"


# --------------------------------------------------------------------------
# Worked example C — corrections converge to the clamp
# --------------------------------------------------------------------------

def test_eight_lasted_longer_reach_clamp():
    m = reduce(lambda acc, _: next_m(acc, "lasted_longer"), range(8), 1.0)
    assert m == pytest.approx(0.2)


# --------------------------------------------------------------------------
# Robustness: timezone handling (naive assumed UTC — the hardening)
# --------------------------------------------------------------------------

def test_naive_and_aware_timestamps_agree():
    aware = PantryItem(1, 1, "milk", "dairy", "2026-07-24T00:00:00+00:00", None, None, False)
    naive = PantryItem(1, 1, "milk", "dairy", "2026-07-24T00:00:00", None, None, False)
    assert item_confidence(aware, 1, NOW) == pytest.approx(item_confidence(naive, 1, NOW))


def test_naive_now_does_not_crash():
    naive_now = datetime(2026, 7, 25)
    aware_item = PantryItem(1, 1, "milk", "dairy", "2026-07-24T00:00:00+00:00", None, None, False)
    assert 0.0 < item_confidence(aware_item, 1, naive_now) <= 1.0


def test_malformed_timestamp_still_raises():
    # A garbage timestamp is corrupt data, not a convention issue. It should
    # surface here (a whole-pantry scan should skip/log the bad row itself).
    bad = PantryItem(1, 1, "milk", "dairy", "not-a-date", None, None, False)
    with pytest.raises(ValueError):
        item_confidence(bad, 1, NOW)


# --------------------------------------------------------------------------
# Robustness: household + time guards
# --------------------------------------------------------------------------

@pytest.mark.parametrize("household", [0, -2])
def test_bad_household_treated_as_one(household):
    assert usable_life_days("dairy", household) == usable_life_days("dairy", 1)


def test_future_timestamp_clamps_to_one():
    # clock skew: bought "in the future" ⇒ t clamped to 0 ⇒ certainly there
    assert item_confidence(make_item("dairy", -5), 1, NOW) == 1.0


def test_fractional_day():
    # milk (U=4) at half a day: x = 0.5/4 = 0.125
    expected = pytest.approx(2.718281828 ** (-LN20 * 0.125 ** 2), abs=1e-6)
    assert item_confidence(make_item("dairy", 0.5), 1, NOW) == expected


def test_usable_life_respects_but_is_not_yet_capped_by_shelf():
    # v1 (Q=1): D <= S everywhere, so consumption drives U and the cap never binds
    assert usable_life_days("dairy", 1) == 4    # D=4, under the S=5 cap
    assert usable_life_days("eggs", 1) == 10     # D=10, under the S=21 cap


# --------------------------------------------------------------------------
# Buckets (§9) and the is_out hard override
# --------------------------------------------------------------------------

@pytest.mark.parametrize("confidence, label", [
    (1.0,    "likely"),
    (0.7,    "likely"),   # boundary is inclusive
    (0.6999, "maybe"),
    (0.3,    "maybe"),    # boundary is inclusive
    (0.2999, "out"),
    (0.0,    "out"),
])
def test_bucket_thresholds(confidence, label):
    assert bucket(confidence) == label


def test_is_out_overrides_a_fresh_curve():
    # reported out at t=0: confidence would be 1.0, but the flag wins
    fresh_but_out = make_item("dairy", 0, is_out=True)
    assert item_confidence(fresh_but_out, 1, NOW) == 1.0
    assert item_bucket(fresh_but_out, 1, NOW) == "out"


# --------------------------------------------------------------------------
# Corrections round-trip through the DB
# --------------------------------------------------------------------------

# `repo` fixture: tests/conftest.py

def _seed_item(repo, category="rice_grains"):
    repo.upsert_user(User(1, 4, None, False, "2026-07-25"))
    repo.upsert_pantry_item(PantryItem(None, 1, "rice", category, NOW.isoformat(), None, None, False))


def test_lasted_longer_lowers_m_and_keeps_item(repo):
    _seed_item(repo)
    assert record_correction(1, "rice", "lasted_longer") == pytest.approx(0.8)
    item = repo.get_pantry_item(1, "rice")
    assert item.decay_lambda == pytest.approx(0.8)
    assert item.is_out is False


def test_ran_out_early_marks_out_but_keeps_row_and_m(repo):
    _seed_item(repo)
    record_correction(1, "rice", "lasted_longer")           # m -> 0.8
    m = record_correction(1, "rice", "ran_out_early")        # m -> 0.96, marked out
    item = repo.get_pantry_item(1, "rice")
    assert m == pytest.approx(0.96)
    assert item.is_out is True
    assert item.decay_lambda is not None       # row kept, m preserved for repurchase


def test_correction_on_missing_item_returns_none(repo):
    _seed_item(repo)
    assert record_correction(1, "ghee", "lasted_longer") is None


def test_repurchase_preserves_m_and_clears_is_out(repo):
    _seed_item(repo)
    record_correction(1, "rice", "ran_out_early")           # m tuned, is_out=1
    before = repo.get_pantry_item(1, "rice").decay_lambda
    # repurchase: same canonical_name, new timestamp
    repo.upsert_pantry_item(PantryItem(None, 1, "rice", "rice_grains", NOW.isoformat(), None, None, False))
    item = repo.get_pantry_item(1, "rice")
    assert item.decay_lambda == pytest.approx(before)  # m survives (household trait)
    assert item.is_out is False                         # a fresh pack is back in stock
