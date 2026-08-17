"""Raw Swiggy SKU name -> canonical ingredient, via the LLM.

Swiggy gives us marketing strings ("Amul Taaza Toned Milk 500 ml") and no
category, so working out that this is `milk`, decaying like `dairy`, is on
us. A keyword matcher fails here ("Dove Milk Cream Bathing Bar" is soap),
so the model reads it.

Expensive per call, but paid once per distinct SKU: the cache layer sits
on top of this. A user's whole order history is one or two calls.
"""

import json
import logging
import re

from openai import OpenAI
from pydantic import BaseModel

from swiggy_buzz.config import DEFAULT_DECAY_DAYS, NIM_API_KEY, NIM_BASE_URL, NIM_FALLBACK_MODEL, NIM_MODEL
from swiggy_buzz.ingester.vocabulary import CANONICAL_NAMES, SKIP, category_for

logger = logging.getLogger(__name__)

# Built once at import: rebuilding 67 names on every call is wasteful, and
# a prompt that varies between runs makes bad answers harder to reproduce.
# Categories come from DEFAULT_DECAY_DAYS, not typed out, so a new decay
# bucket can't leave this prompt stale.
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
"Nandini Quinoa Grain 500 g": {{"canonical": "quinoa", "category": "rice_grains"}}}}

The input data is:
"""


_client = OpenAI(base_url=NIM_BASE_URL, api_key=NIM_API_KEY)

_BATCH_SIZE = 40
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_UNSAFE_RE = re.compile(r"[^a-z0-9_]+")


class Classification(BaseModel):
    canonical: str | None
    category: str

    @property
    def is_food(self) -> bool:
        return self.category != SKIP


def _extract_json(text: str) -> dict | None:
    if not text:
        return None

    cleaned = _FENCE_RE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        logger.warning("no JSON object in model reply: %r", text[:200])
        return None

    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("model reply was not valid JSON (%s): %r", exc, text[:200])
        return None

    if not isinstance(payload, dict):
        logger.warning("model returned %s, expected an object", type(payload).__name__)
        return None
    return payload


def _ask(names) -> dict|None:
    user_prompt = "\n".join(names)
    for model in (NIM_MODEL, NIM_FALLBACK_MODEL):
        for extra in ({"response_format": {"type": "json_object"}}, {}):
            try:
                completion = _client.chat.completions.create(
                    model = model,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                    temperature=0.0,
                    max_tokens=4096,
                    **extra
                )  
            except Exception as e:
                logger.warning("NIM call failed (model=%s, json_mode=%s): %s", model, bool(extra), e)
                continue
            output_model = completion.choices[0].message.content or ""
            result = _extract_json(output_model)
            if result is not None:
                return result
    logger.error("could not classify a batch of %d names", len(names))
    return None


def _clean_canonical(value) -> str|None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    value = _UNSAFE_RE.sub("_", value)
    cleaned = value.strip("_")
    return cleaned or None


def _interpret(payload, names) -> dict[str, Classification]:
    wanted = {}
    for name in names:
        wanted[name.strip().lower()] = name
    result = {}
    for key,value in payload.items():
        name = wanted.get(str(key).strip().lower())
        if name is None:
            logger.warning(f"Bad key found, not in the orignal names: {key}")
            continue
        if not isinstance(value, dict):
            logger.warning("The return value is not in dict/JSON format: key=%r value=%r", name, value)
            continue
        category = value.get('category')
        canonical = _clean_canonical(value.get('canonical'))
        if category == SKIP:
            result[name] = Classification(canonical=None, category=SKIP)
            continue
        known = category_for(canonical) if canonical else None
        if known is not None:
            result[name] = Classification(canonical=canonical, category=known)
            continue
        if canonical is None or category not in DEFAULT_DECAY_DAYS:
            logger.warning("Dropping unusable classification for %r: %r", name, value)
            continue
        result[name] = Classification(canonical=canonical, category=category)
    return result


def classify(raw_names) -> dict[str, Classification]:
    names = [name for name in dict.fromkeys(raw_names) if name and name.strip()]
    if not names:
        return {}
    result = {}
    for i in range(0, len(names), _BATCH_SIZE):
        batch = names[i:i + _BATCH_SIZE]
        payload = _ask(batch)
        if payload is None:
            continue
        result.update(_interpret(payload, batch))
    missing = [name for name in names if name not in result]
    if missing:
        logger.warning("%d of %d names unclassified, e.g. %r", len(missing), len(names), missing[:3])
    return result
