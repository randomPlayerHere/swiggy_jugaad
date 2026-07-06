from dataclasses import dataclass

@dataclass
class User:
    user_id: int
    household_size: int
    diet: str | None
    address_confirmed: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> "User":
        return cls(
            user_id=row["user_id"],
            household_size=row["household_size"],
            diet=row["diet"],
            address_confirmed=bool(row["address_confirmed"]),
            created_at=row["created_at"],
        )

@dataclass
class PantryItem:
    id: int
    user_id: int
    canonical_name: str
    category: str
    last_purchased_at: str
    purchase_qty: float | None
    decay_lambda: float | None
    
    @classmethod
    def from_row(cls, row) -> "PantryItem":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            canonical_name=row["canonical_name"],
            category=row["category"],
            last_purchased_at=row["last_purchased_at"],
            purchase_qty=row["purchase_qty"],
            decay_lambda=row["decay_lambda"],
        )
    
@dataclass
class Correction:
    id: int
    user_id: int
    canonical_name: str
    direction: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Correction":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            canonical_name=row["canonical_name"],
            direction=row["direction"],
            created_at=row["created_at"],
        )

@dataclass
class OrderCache:
    user_id: int
    order_id: str
    raw_json: str
    fetched_at: str

    @classmethod
    def from_row(cls, row) -> "OrderCache":
        return cls(
            user_id=row["user_id"],
            order_id=row["order_id"],
            raw_json=row["raw_json"],
            fetched_at=row["fetched_at"],
        )