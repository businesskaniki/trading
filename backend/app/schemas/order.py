from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
)


# ==========================================================
# BASE SCHEMA
# ==========================================================

class OrderBase(BaseModel):
    """
    Shared fields used by Order schemas.
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

    # ======================================================
    # ORDER VALIDATION
    # ======================================================

    @model_validator(mode="after")
    def validate_order(self):
        """
        Validate fields according to order type.
        """

        # --------------------------------------------------
        # MARKET
        # --------------------------------------------------

        if self.order_type == OrderType.MARKET:

            # A market order does not require a requested
            # price. The execution layer obtains the
            # appropriate market price from the broker.

            return self

        # --------------------------------------------------
        # LIMIT / STOP
        # --------------------------------------------------

        if self.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:

            if self.requested_price is None:
                raise ValueError(
                    "requested_price is required for "
                    "LIMIT and STOP orders."
                )

        return self


# ==========================================================
# CREATE
# ==========================================================

class OrderCreate(OrderBase):
    """
    Payload used when creating a new AQE order.

    Broker-generated fields such as ticket, execution price,
    status, and timestamps are intentionally excluded.
    """

    pass


# ==========================================================
# UPDATE
# ==========================================================

class OrderUpdate(BaseModel):
    """
    Payload used when updating an existing order.
    """

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


# ==========================================================
# RESPONSE
# ==========================================================

class OrderResponse(OrderBase):
    """
    Order representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID

    ticket: int | None

    executed_price: Decimal | None

    status: OrderStatus

    created_at: datetime

    updated_at: datetime