from collections import Counter

from .models import Recipe
from swiggy_buzz.config import RECIPE_DB_PATH
from swiggy_buzz.ingester.vocabulary import CANONICAL_NAMES
import json

def load_recipes_from_dicts(path: str = RECIPE_DB_PATH) -> list[Recipe]:
    with open(path, "r") as f:
        data = json.load(f)
    recipes = [Recipe.model_validate(recipe_data) for recipe_data in data]

    vocab = set(CANONICAL_NAMES)
    unknown_ingredients = {
        recipe.id: unknown
        for recipe in recipes
        if (unknown := [i for i in recipe.ingredients if i not in vocab])
    }
    if unknown_ingredients:
        raise ValueError(
            f"recipes reference ingredients outside the vocabulary: {unknown_ingredients}"
        )

    duplicate_ids = {id_ for id_, count in Counter(r.id for r in recipes).items() if count > 1}
    if duplicate_ids:
        raise ValueError(f"duplicate recipe ids in {path}: {duplicate_ids}")

    return recipes