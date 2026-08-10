from pydantic import BaseModel


class SymbolResponse(BaseModel):

    name: str

    description: str | None = None

    path: str | None = None

    currency_base: str

    currency_profit: str

    currency_margin: str

    digits: int

    point: float

    spread: int

    bid: float

    ask: float

    visible: bool


class TickResponse(BaseModel):

    symbol: str

    bid: float

    ask: float

    last: float

    volume: int

    time: int