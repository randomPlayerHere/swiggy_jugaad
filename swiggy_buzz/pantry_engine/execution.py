from datetime import datetime

from swiggy_buzz.store.models import ScoredItem
from swiggy_buzz.store.repo import get_pantry_item, get_pantry, get_user
from .confidence import item_confidence, item_bucket

def score_pantry_item(user_id: int, canonical_name: str, now: datetime) -> ScoredItem | None:
    user = get_user(user_id)
    if not user:
        return None
    pantry_item = get_pantry_item(user_id, canonical_name)
    if not pantry_item:
        return None
    return ScoredItem(
        pantry_item=pantry_item,
        confidence_score=item_confidence(pantry_item, user.household_size, now),
        bucket=item_bucket(pantry_item, user.household_size, now)
    )


def score_entire_pantry(user_id: int, now: datetime) -> list[ScoredItem] | None:
    user = get_user(user_id)
    if not user:
        return None
    pantry = get_pantry(user_id)
    result_scores = list()
    for item in pantry:
        result_scores.append(
            ScoredItem(
                pantry_item=item,
                confidence_score=item_confidence(item, user.household_size, now),
                bucket=item_bucket(item, user.household_size, now)
            )
        )
    return result_scores
