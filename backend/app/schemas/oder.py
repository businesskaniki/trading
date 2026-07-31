from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import OrderSide
from app.core.constants import OrderStatus
from app.core.constants import OrderType


# ==========================================================
# Base Schema
# ==========================================================

class OrderBase(BaseModel):
    """
    Shared Order fields.
    """

    strategy: str = Field(
        ...,
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

    volume: Decimal

    requested_price: Decimal

    executed_price: Decimal | None = None

    stop_loss: Decimal | None = None

    take_profit: Decimal | None = None


# ==========================================================
# Create Schema
# ==========================================================

class OrderCreate(OrderBase):
    """
    Payload used when creating an order.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class OrderUpdate(BaseModel):
    """
    Payload used when updating an order.
    """

    strategy: str | None = Field(
        default=None,
        max_length=100,
    )

    comment: str | None = Field(
        default=None,
        max_length=255,
    )

    order_type: OrderType | None = None

    side: OrderSide | None = None

    volume: Decimal | None = None

    requested_price: Decimal | None = None

    executed_price: Decimal | None = None

    stop_loss: Decimal | None = None

    take_profit: Decimal | None = None

    status: OrderStatus | None = None


# ==========================================================
# Response Schema
# ==========================================================

class OrderResponse(OrderBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    ticket: int | None

    status: OrderStatus

    created_at: datetime

    updated_at: datetime