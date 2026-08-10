from typing import Optional

from pydantic import BaseModel


class OrderRequest(BaseModel):

    symbol: str

    volume: float

    order_type: int

    price: float

    sl: Optional[float] = None

    tp: Optional[float] = None

    deviation: int = 20

    magic: int = 0

    comment: str = ""


class OrderResponse(BaseModel):

    ticket: int

    symbol: str

    volume: float

    price_open: float

    sl: float

    tp: float

    order_type: int

    state: int

    comment: str