"""Recipe scoring/ranking tests. Uses hand-built ScoredItems rather than real
pantry_engine output; scoring.py only cares about the bucket string, so
these stay decoupled from decay math changes."""

import pytest

from swiggy_buzz.recipe.loader import load_recipes_from_dicts
from swiggy_buzz.recipe.models import Recipe
from swiggy_buzz.recipe.scoring import (
    missing_ingredients,
    owned_fraction,
    rank_recipes,
    score,
)
from swiggy_buzz.store.models import PantryItem, ScoredItem


def make_scored(canonical_name: str, bucket: str) -> ScoredItem:
    item = PantryItem(1, 1, canonical_name, "produce", "2026-08-01T00:00:00+00:00", None, None, False)
    return ScoredItem(pantry_item=item, confidence_score=0.5, bucket=bucket)


def make_recipe(id_="r", ingredients=None, diet="vegan", prep_time_minutes=20) -> Recipe:
    return Recipe(
        id=id_,
        name=id_,
        ingredients=ingredients or [],
        diet=diet,
        prep_time_minutes=prep_time_minutes,
        tags=[],
    )


# --------------------------------------------------------------------------
# owned_fraction / missing_ingredients
# --------------------------------------------------------------------------

def test_owned_fraction_weights_by_bucket():
    recipe = make_recipe(ingredients=["onion", "tomato", "salt", "oil"])
    pantry = {
        "onion": make_scored("onion", "likely"),
        "tomato": make_scored("tomato", "maybe"),
        "salt": make_scored("salt", "out"),
        # "oil" absent entirely
    }
    # likely=1.0, maybe=0.5, out=0.0, missing=0.0 -> (1.0+0.5+0+0)/4
    assert owned_fraction(recipe, pantry) == pytest.approx(0.375)


def test_owned_fraction_empty_pantry_is_zero():
    recipe = make_recipe(ingredients=["onion", "tomato"])
    assert owned_fraction(recipe, {}) == 0.0


def test_missing_ingredients_includes_absent_and_out():
    recipe = make_recipe(ingredients=["onion", "tomato", "salt"])
    pantry = {"onion": make_scored("onion", "likely"), "salt": make_scored("salt", "out")}
    assert missing_ingredients(recipe, pantry) == ["tomato", "salt"]


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------

def test_score_prefers_faster_recipe_when_everything_else_equal():
    fast = make_recipe("fast", ingredients=["onion"], prep_time_minutes=10)
    slow = make_recipe("slow", ingredients=["onion"], prep_time_minutes=40)
    pantry = {"onion": make_scored("onion", "likely")}
    assert score(fast, pantry, prep_time_min=10) > score(slow, pantry, prep_time_min=10)


def test_score_fastest_recipe_gets_full_speed_term():
    recipe = make_recipe(ingredients=[], prep_time_minutes=10)
    # owned_fraction=0 (no ingredients contribute), taste_fit stub=1.0, speed=10/10=1.0
    assert score(recipe, {}, prep_time_min=10) == pytest.approx(2.0)


# --------------------------------------------------------------------------
# rank_recipes: diet hierarchy + sort order
# --------------------------------------------------------------------------

def test_rank_recipes_vegan_user_only_sees_vegan():
    recipes = [make_recipe("v", diet="vegan"), make_recipe("nv", diet="veg")]
    ranked = rank_recipes(recipes, [], diet="vegan")
    assert [r.id for r, _, _ in ranked] == ["v"]


def test_rank_recipes_veg_user_sees_vegan_and_veg_but_not_egg():
    recipes = [make_recipe("v", diet="vegan"), make_recipe("g", diet="veg"), make_recipe("e", diet="egg")]
    ranked = rank_recipes(recipes, [], diet="veg")
    assert {r.id for r, _, _ in ranked} == {"v", "g"}


def test_rank_recipes_no_diet_means_no_filter():
    recipes = [make_recipe("v", diet="vegan"), make_recipe("e", diet="egg")]
    ranked = rank_recipes(recipes, [], diet=None)
    assert {r.id for r, _, _ in ranked} == {"v", "e"}


def test_rank_recipes_sorted_descending_by_score():
    recipes = [make_recipe("slow", ingredients=[], prep_time_minutes=40),
               make_recipe("fast", ingredients=[], prep_time_minutes=10)]
    ranked = rank_recipes(recipes, [], diet=None)
    assert [r.id for r, _, _ in ranked] == ["fast", "slow"]


def test_rank_recipes_returns_missing_ingredients_per_recipe():
    recipe = make_recipe("r", ingredients=["onion", "tomato"])
    pantry = [make_scored("onion", "likely")]
    ranked = rank_recipes([recipe], pantry, diet=None)
    assert ranked[0][2] == ["tomato"]


# --------------------------------------------------------------------------
# integration: real seed data loads and ranks without error
# --------------------------------------------------------------------------

def test_seed_recipes_load_and_rank():
    recipes = load_recipes_from_dicts()
    ranked = rank_recipes(recipes, [], diet=None)
    assert len(ranked) == len(recipes)
    assert all(0 <= s <= 3 for _, s, _ in ranked)
