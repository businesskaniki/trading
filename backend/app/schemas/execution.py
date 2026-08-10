from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class ExecutionOrder(BaseModel):
    """
    Broker-agnostic order representation used by AQE.
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=32,
    )

    side: OrderSide

    order_type: OrderType = OrderType.MARKET

    volume: Decimal = Field(
        ...,
        gt=0,
    )

    price: Decimal | None = Field(
        default=None,
        gt=0,
    )

    stop_loss: Decimal | None = Field(
        default=None,
        gt=0,
    )

    take_profit: Decimal | None = Field(
        default=None,
        gt=0,
    )

    deviation: int = Field(
        default=20,
        ge=0,
    )

    magic_number: int = Field(
        default=10001,
        ge=0,
    )

    comment: str | None = Field(
        default="AQE",
        max_length=255,
    )

    @model_validator(mode="after")
    def validate_order(self):

        if self.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        } and self.price is None:

            raise ValueError(
                "Price is required for LIMIT and STOP orders."
            )

        return self

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ExecutionResult(BaseModel):
    """
    Standard response returned by a broker execution.
    """

    status: ExecutionStatus

    broker: str

    order_id: int | None = None

    position_id: int | None = None

    symbol: str | None = None

    volume: Decimal | None = None

    price: Decimal | None = None

    message: str | None = None

    raw_response: dict | None = None