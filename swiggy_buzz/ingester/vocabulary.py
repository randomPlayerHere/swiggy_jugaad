"""The canonical ingredient vocabulary — the shared language of the app.

Two consumers, and they must agree exactly:

  * the ingester, which constrains the LLM to these names, so a product is
    "tomato" every time and not "tomatoes" on Tuesday. Each distinct string
    becomes its own pantry_items row with its own decay clock (the table is
    UNIQUE on user_id + canonical_name), so drift silently splits one
    ingredient into several half-confident ones.
  * the recipe DB, which lists ingredients by these same names. A recipe
    asking for "wheat flour" against a pantry holding "atta" scores 0% owned.

Swiggy never tells us a category — no Instamart tool returns one, verified
against the live server — so every category here is our own judgement call.

Categories are *decay buckets*, not food groups: the only question each one
answers is "how fast does this leave the kitchen?" That is why ghee sits with
oil rather than dairy, and why sugar and tea sit under spices. Read them as
shelf-life classes and the odd-looking placements come out right. Values must
be keys of config.DEFAULT_DECAY_DAYS — checked at import, below.
"""

from swiggy_buzz.config import DEFAULT_DECAY_DAYS

# Pseudo-category for things that are not food: notebooks, shampoo, batteries.
# Not a real bucket — nothing with this category ever reaches the pantry. It
# exists so "known non-food" is a stored, cacheable answer rather than a miss,
# otherwise every ingest re-asks the LLM about the same bar of soap.
SKIP = "skip"

VOCABULARY: dict[str, str] = {
    # --- dairy: days, and the fridge is the only thing slowing it down ---
    "milk": "dairy",
    "curd": "dairy",
    "paneer": "dairy",
    "butter": "dairy",
    "cheese": "dairy",
    "cream": "dairy",

    # --- produce: fastest bucket; assume nothing survives the week ---
    "onion": "produce",
    "tomato": "produce",
    "potato": "produce",
    "garlic": "produce",
    "ginger": "produce",
    "green_chilli": "produce",
    "coriander": "produce",
    "mint": "produce",
    "spinach": "produce",
    "cauliflower": "produce",
    "cabbage": "produce",
    "carrot": "produce",
    "capsicum": "produce",
    "brinjal": "produce",
    "okra": "produce",
    "peas": "produce",
    "cucumber": "produce",
    "lemon": "produce",
    "banana": "produce",
    "apple": "produce",
    "mushroom": "produce",

    # --- bread ---
    "bread": "bread",
    "pav": "bread",
    "bun": "bread",

    # --- eggs ---
    "egg": "eggs",

    # --- rice_grains: flours and dry staples, bought big, used slowly ---
    "rice": "rice_grains",
    "atta": "rice_grains",
    "maida": "rice_grains",
    "suji": "rice_grains",
    "besan": "rice_grains",
    "poha": "rice_grains",
    "dalia": "rice_grains",
    "oats": "rice_grains",
    "vermicelli": "rice_grains",

    # --- pulses: the slowest of the staples ---
    "toor_dal": "pulses",
    "moong_dal": "pulses",
    "chana_dal": "pulses",
    "urad_dal": "pulses",
    "masoor_dal": "pulses",
    "rajma": "pulses",
    "chole": "pulses",

    # --- oil: one generic entry on purpose. "Do I have oil?" is the question
    # a recipe asks; mustard vs sunflower vs refined would fragment the pantry
    # into three half-stocked rows answering it worse. Ghee lives here for its
    # shelf life, not its origin.
    "oil": "oil",
    "ghee": "oil",

    # --- spices: the near-immortal shelf. Salt, sugar, tea and coffee are not
    # spices, but they deplete on the same ~90-day timescale, which is the only
    # thing this key controls.
    "salt": "spices",
    "sugar": "spices",
    "turmeric": "spices",
    "red_chilli_powder": "spices",
    "coriander_powder": "spices",
    "cumin": "spices",
    "garam_masala": "spices",
    "mustard_seeds": "spices",
    "black_pepper": "spices",
    "hing": "spices",
    "tea": "spices",
    "coffee": "spices",

    # --- snacks: bought to be eaten, and they are ---
    "biscuit": "snacks",
    "namkeen": "snacks",
    "chips": "snacks",
    "chocolate": "snacks",
    "noodles": "snacks",
    "cornflakes": "snacks",
}

# Sorted so the LLM prompt is byte-stable between runs — a prompt that shuffles
# itself defeats any prompt caching and makes bad answers harder to reproduce.
CANONICAL_NAMES: list[str] = sorted(VOCABULARY)


def category_for(canonical_name: str) -> str | None:
    """Category for a known ingredient, or None if it is not in the vocabulary.

    None is a real answer, not a failure: the LLM is allowed to coin a name
    that isn't on the list yet, and when it does it must supply the category
    itself (see the ingester's LLM step).
    """
    return VOCABULARY.get(canonical_name)


def _validate() -> None:
    """Fail loudly at import if a category isn't a real decay bucket.

    A typo like "diary" would not raise anywhere else — usable_life_days()
    falls back to D=21 for unknown categories and merely logs, so milk would
    quietly decay like rice for the life of the project. Cheap to check once.
    """
    unknown = {
        name: category
        for name, category in VOCABULARY.items()
        if category not in DEFAULT_DECAY_DAYS
    }
    if unknown:
        raise ValueError(
            f"vocabulary categories missing from config.DEFAULT_DECAY_DAYS: {unknown}"
        )


_validate()
