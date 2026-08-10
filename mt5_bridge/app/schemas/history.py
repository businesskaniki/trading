from pydantic import BaseModel


class DealResponse(BaseModel):

    ticket: int

    order: int

    symbol: str

    volume: float

    price: float

    profit: float

    commission: float

    swap: float

    comment: str

    time: int


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