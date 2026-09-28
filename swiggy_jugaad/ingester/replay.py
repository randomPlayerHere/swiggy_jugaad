"""Sample order history for demos, in the raw shape get_orders returns.

Swiggy only exposes ~15 days of order history, so an account that hasn't
ordered lately syncs an empty pantry. A replay file stands in for that one
fetch and nothing else: parse, classify, decay and rank all run as usual.

Dates are stored as days_ago rather than timestamps, so the same file gives
the same pantry shape on whatever day it's replayed.
"""

import json
from datetime import datetime, timedelta, timezone


def load_replay_orders(path: str, now: datetime | None = None) -> list[dict]:
    """Orders from `path`, newest first, each stamped createdAt = now - days_ago."""
    now = now or datetime.now(timezone.utc)
    with open(path) as f:
        orders = json.load(f)
    raw = [
        {
            "orderId": order["orderId"],
            "createdAt": (now - timedelta(days=order["days_ago"])).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": order.get("status", "DELIVERED"),
            "items": order["items"],
        }
        for order in orders
    ]
    return sorted(raw, key=lambda o: o["createdAt"], reverse=True)
