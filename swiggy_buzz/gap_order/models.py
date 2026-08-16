from dataclasses import dataclass, field


@dataclass
class CartLine:
    ingredient: str
    spin_id: str
    sku_id: str
    name: str
    price: float
    qty: int


@dataclass
class UnresolvedItem:
    ingredient: str
    reason: str
    similar: list[dict] = field(default_factory=list)


@dataclass
class OrderSummary:
    lines: list[CartLine]
    dropped_for_cap: list[CartLine]
    total: float
    order_id: str | None = None
