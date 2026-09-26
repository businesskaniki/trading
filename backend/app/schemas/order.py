from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import OrderSide, OrderStatus, OrderType


class OrderBase(BaseModel):
    """
    Fields required to define an AQE order.
    """

    strategy: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    comment: str | None = Field(
        default=None,
        max_length=255,
    )

    account_id: UUID
    symbol_id: UUID

    order_type: OrderType
    side: OrderSide

    volume: Decimal = Field(
        ...,
        gt=0,
    )

    requested_price: Decimal | None = Field(
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

    @model_validator(mode="after")
    def validate_order(self) -> OrderBase:
        """
        Validate fields according to the order type.

        MARKET orders obtain their execution price from the broker.

        LIMIT and STOP orders require an explicit requested price.
        """

        if self.order_type == OrderType.MARKET:
            return self

        if self.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            if self.requested_price is None:
                raise ValueError(
                    "requested_price is required for " "LIMIT and STOP orders."
                )

        return self


class OrderCreate(OrderBase):
    """
    Payload used to create a new AQE order.
    """

    pass


class OrderUpdate(BaseModel):
    """
    Fields that may be updated before broker execution.

    Broker identifiers and lifecycle state are intentionally excluded.
    Those fields are controlled by the execution layer.
    """

    model_config = ConfigDict(extra="forbid")

    strategy: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    comment: str | None = Field(
        default=None,
        max_length=255,
    )

    order_type: OrderType | None = None
    side: OrderSide | None = None

    volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    requested_price: Decimal | None = Field(
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


class OrderStatusUpdate(BaseModel):
    """
    Explicit order-status update payload.

    This remains available for administrative/internal workflows.
    Normal broker-driven lifecycle changes should be performed by
    OrderExecutionService.
    """

    status: OrderStatus


class OrderResponse(OrderBase):
    """
    API representation of a persisted AQE order.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    # ------------------------------------------------------------------
    # Broker identifiers
    # ------------------------------------------------------------------

    broker_order_id: int | None = None
    broker_deal_id: int | None = None
    broker_position_id: int | None = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    executed_price: Decimal | None = None

    status: OrderStatus

    created_at: datetime
    updated_at: datetime
