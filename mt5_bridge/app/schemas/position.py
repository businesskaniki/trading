from typing import Optional

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


class PositionCloseResponse(BaseModel):

    ticket: int
    retcode: int
    comment: str
    order: int
    deal: int


class PositionModifyRequest(BaseModel):

    sl: Optional[float] = None
    tp: Optional[float] = None

class PositionModifyResponse(BaseModel):

    ticket: int
    symbol: str
    sl: float
    tp: float
    retcode: int
    comment: str