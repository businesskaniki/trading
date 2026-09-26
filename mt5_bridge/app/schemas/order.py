from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# MT5 order types currently supported by the AQE bridge.
MARKET_BUY = 0
MARKET_SELL = 1
BUY_LIMIT = 2
SELL_LIMIT = 3
BUY_STOP = 4
SELL_STOP = 5

SUPPORTED_ORDER_TYPES = {
    MARKET_BUY,
    MARKET_SELL,
    BUY_LIMIT,
    SELL_LIMIT,
    BUY_STOP,
    SELL_STOP,
}

PENDING_ORDER_TYPES = {
    BUY_LIMIT,
    SELL_LIMIT,
    BUY_STOP,
    SELL_STOP,
}


class OrderRequest(BaseModel):
    """
    Normalized order request received by the MT5 bridge.

    The AQE adapter is responsible for translating its generic
    ExecutionOrder into this MT5-specific contract.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=32,
    )

    volume: float = Field(
        ...,
        gt=0,
    )

    order_type: int = Field(
        ...,
        ge=0,
    )

    price: Optional[float] = Field(
        default=None,
        gt=0,
    )

    sl: Optional[float] = None

    tp: Optional[float] = None

    deviation: int = Field(
        default=20,
        ge=0,
        le=10000,
    )

    magic: int = Field(
        default=0,
        ge=0,
    )

    comment: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("symbol cannot be empty")

        return value

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        return " ".join(value.split())[:31]

    @model_validator(mode="after")
    def validate_order(self) -> "OrderRequest":
        if self.order_type not in SUPPORTED_ORDER_TYPES:
            raise ValueError(f"unsupported MT5 order type: {self.order_type}")

        if self.order_type in PENDING_ORDER_TYPES and self.price is None:
            raise ValueError("price is required for pending orders")

        if self.sl is not None and self.sl <= 0:
            raise ValueError("sl must be greater than zero")

        if self.tp is not None and self.tp <= 0:
            raise ValueError("tp must be greater than zero")

        return self


class OrderResponse(BaseModel):
    """
    Normalized MT5 order submission response.

    MT5 distinguishes between:

        order_id
            The MT5 order ticket.

        deal_id
            The executed deal/transaction identifier.

        position_id
            The resulting position identifier when applicable.

    These identifiers remain separate because they represent
    different MT5 objects and have different lifecycles.
    """

    model_config = ConfigDict(extra="ignore")

    order_id: Optional[int] = None

    deal_id: Optional[int] = None

    position_id: Optional[int] = None

    symbol: str

    volume: float

    price_open: float

    sl: Optional[float] = None

    tp: Optional[float] = None

    order_type: int

    state: int

    comment: str
