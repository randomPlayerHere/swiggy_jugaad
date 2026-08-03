from pydantic import BaseModel
from datetime import datetime

DELIVERED = "DELIVERED"

class PurchasedItem(BaseModel):
    raw_name :str
    quantity :int = 1
    sku_id :str | None = None

class ParsedOrder(BaseModel):
    order_id :str
    purchased_at : datetime
    status : str
    items :list[PurchasedItem]

    @property
    def is_delivered(self) -> bool:
        return self.status == DELIVERED
