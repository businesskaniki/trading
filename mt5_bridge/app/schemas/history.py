from pydantic import BaseModel


class HistoryOrderResponse(BaseModel):
    ticket: int
    symbol: str
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    state: int
    comment: str
    time_setup: int


class DealResponse(BaseModel):
    ticket: int
    order: int
    position_id: int | None = None
    symbol: str
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    comment: str
    time: int
    entry: int | None = None