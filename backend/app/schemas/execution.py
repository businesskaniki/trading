from __future__ import annotations

from decimal import Decimal
from enum import Enum
from uuid import UUID

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
    Normalized order instruction sent to the execution engine.

    ExecutionOrder represents the intent to execute an order.
    Broker-specific identifiers do not belong here because they do
    not exist until the broker accepts/submits the order.
    """

    symbol: str = Field(..., min_length=1, max_length=32)
    account_id: UUID | None = None
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    volume: Decimal = Field(..., gt=0)

    # Required for pending orders, optional for market orders.
    price: Decimal | None = Field(default=None, gt=0)

    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)

    deviation: int = Field(default=20, ge=0)
    magic_number: int = Field(default=10001, ge=0)
    comment: str | None = Field(default="AQE", max_length=255)

    @model_validator(mode="after")
    def validate_order(self) -> ExecutionOrder:
        """
        Pending orders require an explicit entry price.
        Market orders obtain their execution price from the broker.
        """

        if self.order_type in {OrderType.LIMIT, OrderType.STOP}:
            if self.price is None:
                raise ValueError("Price is required for LIMIT and STOP orders.")

        return self


class ExecutionStatus(str, Enum):
    """
    Result status returned by the execution layer.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ExecutionResult(BaseModel):
    """
    Normalized result returned after a broker execution attempt.

    Broker identifiers are deliberately separated because they
    represent different MT5 entities:

        broker_order_id
            Broker order/ticket.

        broker_deal_id
            Executed transaction/deal.

        broker_position_id
            Resulting open position, when applicable.

    These values may legitimately be None depending on the order
    type and broker execution state.
    """

    status: ExecutionStatus
    broker: str

    broker_order_id: int | None = None
    broker_deal_id: int | None = None
    broker_position_id: int | None = None

    symbol: str | None = None
    volume: Decimal | None = None
    price: Decimal | None = None

    message: str | None = None
    raw_response: dict | None = None
