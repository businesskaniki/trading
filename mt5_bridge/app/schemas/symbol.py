from pydantic import BaseModel


class SymbolResponse(BaseModel):

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name: str

    description: str | None = None

    path: str | None = None

    # ------------------------------------------------------------------
    # Currencies
    # ------------------------------------------------------------------

    currency_base: str

    currency_profit: str

    currency_margin: str

    # ------------------------------------------------------------------
    # Price / precision
    # ------------------------------------------------------------------

    digits: int

    point: float

    # ------------------------------------------------------------------
    # Current market data
    # ------------------------------------------------------------------

    spread: int

    bid: float

    ask: float

    # ------------------------------------------------------------------
    # MT5 Market Watch state
    # ------------------------------------------------------------------

    visible: bool

    # ------------------------------------------------------------------
    # Trading specification
    # ------------------------------------------------------------------

    trade_tick_size: float | None = None

    trade_tick_value: float | None = None

    trade_tick_value_profit: float | None = None

    trade_tick_value_loss: float | None = None

    trade_contract_size: float | None = None

    # ------------------------------------------------------------------
    # Volume specification
    # ------------------------------------------------------------------

    volume_min: float | None = None

    volume_max: float | None = None

    volume_step: float | None = None

    # ------------------------------------------------------------------
    # Trading constraints
    # ------------------------------------------------------------------

    trade_stops_level: int | None = None

    trade_freeze_level: int | None = None


class TickResponse(BaseModel):

    symbol: str

    bid: float

    ask: float

    last: float

    volume: int

    time: int


class CandleResponse(BaseModel):

    time: int

    open: float

    high: float

    low: float

    close: float

    volume: int

    spread: int
