
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any
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
    Broker-independent instruction to execute an order.

    This represents requested intent, not an actual broker execution.
    """

    symbol: str = Field(..., min_length=1, max_length=32)
    account_id: UUID | None = None

    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    volume: Decimal = Field(..., gt=0)

    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)

    deviation: int = Field(default=20, ge=0)
    magic_number: int = Field(default=10001, ge=0)
    comment: str | None = Field(default="AQE", max_length=255)

    @model_validator(mode="after")
    def validate_order(self) -> ExecutionOrder:
        if self.order_type in {OrderType.LIMIT, OrderType.STOP}:
            if self.price is None:
                raise ValueError(
                    "Price is required for LIMIT and STOP orders."
                )

        return self


class ExecutionStatus(str, Enum):
    """
    Normalized result of a broker submission or execution attempt.

    SUCCESS:
        Confirmed full execution.

    PLACED:
        Broker reports that an order was placed, but full execution
        has not been confirmed.

    PARTIALLY_FILLED:
        Broker confirms that only part of the requested volume executed.

    UNKNOWN:
        The outcome cannot safely be established. Reconciliation is
        required before deciding whether a retry is safe.

    NOT_SUBMITTED:
        The bridge confirms the broker submission boundary was not crossed.

    REJECTED:
        The broker explicitly rejected the request.

    FAILED:
        Legacy failure status. New execution code should use a more
        precise status whenever the outcome is known.
    """

    SUCCESS = "SUCCESS"
    PLACED = "PLACED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    UNKNOWN = "UNKNOWN"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ExecutionResult(BaseModel):
    """
    Normalized result of a broker operation.

    volume:
        Broker-confirmed executed volume. None means that the result
        does not confirm any executed quantity.

    requested_volume:
        Original order volume, when known.

    price:
        Confirmed execution price. It must not be populated merely
        with the submitted or requested entry price.

    The order, deal, and position identifiers refer to distinct
    broker entities.
    """

    status: ExecutionStatus
    broker: str

    broker_order_id: int | None = None
    broker_deal_id: int | None = None
    broker_position_id: int | None = None

    symbol: str | None = None

    requested_volume: Decimal | None = None
    volume: Decimal | None = None
    price: Decimal | None = None

    retcode: int | None = None
    request_id: int | None = None
    retcode_external: int | None = None

    message: str | None = None
    raw_response: dict[str, Any] | None = None
