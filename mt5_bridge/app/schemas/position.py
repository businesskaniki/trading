from pydantic import BaseModel


class PositionResponse(BaseModel):
    ticket: int
    symbol: str
    volume: float

    price_open: float
    price_current: float

    sl: float
    tp: float

    profit: float
    swap: float

    comment: str

    type: int