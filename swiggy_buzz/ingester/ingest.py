from .models import ParsedOrder

def collect_raw_names(orders: list[ParsedOrder]) -> list[str]:
    raw_names = []
    for order in orders:
        for item in order.items:
            raw_names.append(item.raw_name)
    return list(dict.fromkeys(raw_names))
