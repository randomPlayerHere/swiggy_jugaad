"""Raw Swiggy SKU name -> canonical ingredient, via the LLM.

Swiggy hands us marketing strings ("Amul Taaza Toned Milk 500 ml") and no
category of any kind, so working out that this is `milk`, and that milk decays
like `dairy`, is entirely our problem. A keyword matcher loses this fight —
"Dove Milk Cream Bathing Bar" is soap — so the model does the reading.

Expensive per call, but only ever paid once per distinct SKU: the cache layer
sits on top of this. A user's whole order history is one or two calls.
"""

from swiggy_buzz.config import DEFAULT_DECAY_DAYS
from swiggy_buzz.ingester.vocabulary import CANONICAL_NAMES, SKIP

# Built once at import: 67 ingredient names is a lot of string to rebuild on
# every call, and a prompt that varies between runs makes a bad answer harder
# to reproduce. Categories are read off DEFAULT_DECAY_DAYS rather than typed
# out, so adding a decay bucket to config can never leave this prompt stale.
_CATEGORIES = ", ".join(sorted(DEFAULT_DECAY_DAYS))

SYSTEM_PROMPT = f"""You classify grocery products for an Indian kitchen-inventory app.

You are given raw product names exactly as they appear on a Swiggy Instamart
receipt — brand names, pack sizes and marketing text included. For each one,
work out which pantry ingredient it is, or say it is not food at all.

Reply with ONE JSON object and nothing else: no prose, no markdown fences.

Each key is a product name copied EXACTLY as given, character for character.
Each value is an object of this shape:

    {{"canonical": <string or null>, "category": <string>}}

Rules:

1. Prefer a canonical name from this list, used exactly as written:
{", ".join(CANONICAL_NAMES)}

2. If the product is not food — soap, shampoo, cosmetics, stationery, cleaning
   supplies, utensils, pet supplies, medicine — answer:
   {{"canonical": null, "category": "{SKIP}"}}

3. If it IS food but nothing on the list fits, invent a short canonical name:
   lowercase, underscores instead of spaces, singular, no brand, no pack size.
   Then choose its category from: {_CATEGORIES}

4. Answer for every product name given, exactly once. Do not add, merge, drop
   or reword any key.

The category describes how fast a household uses the item up, not which food
group it belongs to. Ghee is "oil" because it keeps like oil. Sugar, salt and
tea are "spices" because they last for months.

Judge the product as a whole, not by words inside it: "Dove Milk Cream Bathing
Bar" is soap, "coconut oil" is oil rather than produce, and "milk chocolate" is
a snack rather than dairy.

Example input:
Amul Taaza Toned Milk 500 ml
Dove Milk Cream Beauty Bathing Bar 100 g
Nandini Quinoa Grain 500 g

Example output:
{{"Amul Taaza Toned Milk 500 ml": {{"canonical": "milk", "category": "dairy"}}, \
"Dove Milk Cream Beauty Bathing Bar 100 g": {{"canonical": null, "category": "{SKIP}"}}, \
"Nandini Quinoa Grain 500 g": {{"canonical": "quinoa", "category": "rice_grains"}}}}"""
