"""JSON recipe DB + scoring/ranking.

score = %ingredients_owned + taste fit + 1/prep_time, with diet filters.
"""

from swiggy_buzz.recipe.loader import load_recipes_from_dicts
from swiggy_buzz.recipe.models import Recipe
from swiggy_buzz.recipe.scoring import (
    missing_ingredients,
    owned_fraction,
    rank_recipes,
    score,
    taste_fit,
)

__all__ = [
    "Recipe",
    "load_recipes_from_dicts",
    "owned_fraction",
    "missing_ingredients",
    "taste_fit",
    "score",
    "rank_recipes",
]
