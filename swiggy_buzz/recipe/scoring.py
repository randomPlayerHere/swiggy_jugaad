"""Recipe scoring/ranking: score = %owned + taste fit + 1/prep_time, with a
hard diet filter applied before scoring (CLAUDE.md, recipe/__init__.py).
"""

from swiggy_buzz.store.models import ScoredItem

from .models import Recipe

# Weight for an ingredient's contribution to owned_fraction, by pantry bucket
# (pantry_engine.confidence.bucket). "out" contributes 0, same as "missing":
# a hard override the household set explicitly.
BUCKET_WEIGHT = {"likely": 1.0, "maybe": 0.5, "out": 0.0}

# Term weights for score(). Equal by default; tune here, not inline, so the
# rationale stays in one place if these ever need to change (pantry_engine's
# MATH.md documents constants the same way).
WEIGHT_OWNED = 1.0
WEIGHT_TASTE = 1.0
WEIGHT_SPEED = 1.0

# Diet order, most to least restrictive: vegan < veg < egg < non_veg. A
# user's diet is a ceiling on what they'll see, not an exact match, so a
# vegetarian still sees vegan recipes.
DIET_HIERARCHY = ["vegan", "veg", "egg", "non_veg"]


def _pantry_lookup(scored_items: list[ScoredItem]) -> dict[str, ScoredItem]:
    """{canonical_name: ScoredItem}, last one wins if somehow duplicated.
    Callers pass one user's pantry, which is already unique per the DB schema."""
    return {s.pantry_item.canonical_name: s for s in scored_items}


def _diet_compatible(user_diet: str | None, recipe_diet: str) -> bool:
    """No stated diet ⇒ no restriction. Otherwise the recipe's diet must sit
    at or below the user's diet on DIET_HIERARCHY."""
    if user_diet is None:
        return True
    return DIET_HIERARCHY.index(recipe_diet) <= DIET_HIERARCHY.index(user_diet)


def owned_fraction(recipe: Recipe, pantry: dict[str, ScoredItem]) -> float:
    """Weighted fraction of recipe.ingredients the pantry likely/maybe has.
    An ingredient missing from the pantry entirely counts the same as "out"."""
    if not recipe.ingredients:
        return 0.0
    total = sum(
        BUCKET_WEIGHT[pantry[ing].bucket]
        for ing in recipe.ingredients
        if ing in pantry
    )
    return total / len(recipe.ingredients)


def missing_ingredients(recipe: Recipe, pantry: dict[str, ScoredItem]) -> list[str]:
    """Canonical names gap_order should shop for: absent from the pantry, or
    present but flagged "out"."""
    return [
        ing for ing in recipe.ingredients
        if ing not in pantry or pantry[ing].bucket == "out"
    ]


def taste_fit(recipe: Recipe) -> float:
    """Stub: no taste-preference signal exists on User yet. Returns a constant
    so this term doesn't skew ranking. Wire this to a real signal once one
    exists."""
    return 1.0


def score(recipe: Recipe, pantry: dict[str, ScoredItem], prep_time_min: int) -> float:
    """%owned + taste fit + 1/prep_time, each term normalized to ~[0, 1] so
    none dominates. Speed term is (fastest recipe's time / this recipe's
    time), so the fastest recipe in the candidate set scores 1.0 and slower
    recipes scale down: same shape as 1/prep_time, anchored to the same
    scale as the other two terms."""
    owned = owned_fraction(recipe, pantry)
    taste = taste_fit(recipe)
    speed = prep_time_min / recipe.prep_time_minutes
    return WEIGHT_OWNED * owned + WEIGHT_TASTE * taste + WEIGHT_SPEED * speed


def rank_recipes(
    recipes: list[Recipe],
    scored_items: list[ScoredItem],
    diet: str | None,
) -> list[tuple[Recipe, float, list[str]]]:
    """Hard-filter by diet, then score and sort descending. Third tuple
    element is the missing-ingredient list gap_order needs to shop for that
    recipe."""
    candidates = [r for r in recipes if _diet_compatible(diet, r.diet)]
    if not candidates:
        return []

    pantry = _pantry_lookup(scored_items)
    prep_time_min = min(r.prep_time_minutes for r in candidates)

    ranked = [
        (r, score(r, pantry, prep_time_min), missing_ingredients(r, pantry))
        for r in candidates
    ]
    ranked.sort(key=lambda entry: entry[1], reverse=True)
    return ranked
