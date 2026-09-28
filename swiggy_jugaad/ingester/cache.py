from swiggy_jugaad.store.repo import cache_sku, get_cached_skus
from .normalize import classify, Classification

def classify_cached(raw_names: list[str]) -> dict[str, Classification]:
    cached = get_cached_skus(raw_names)
    results =  {
        name: Classification(canonical=canonical, category=category)
        for name, (canonical, category) in cached.items()
    }
    not_cached = [raw_name for raw_name in raw_names if raw_name not in results.keys()]
    if not not_cached:
        return results
    new_sku_data = classify(not_cached)
    for name,c in new_sku_data.items():
        cache_sku(name, c.canonical, c.category)
    results.update(new_sku_data)
    return results


