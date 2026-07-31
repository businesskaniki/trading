from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import PositionDirection
from app.core.constants import PositionStatus


# ==========================================================
# Base Schema
# ==========================================================

class PositionBase(BaseModel):
    """
    Shared Position fields.
    """

    ticket: int

    broker_position_id: str | None = Field(
        default=None,
        max_length=100,
    )

    strategy: str = Field(
        ...,
        max_length=100,
    )

    account_id: UUID

    symbol_id: UUID

    order_id: UUID

    direction: PositionDirection

    volume: Decimal

    current_volume: Decimal

    entry_price: Decimal

    current_price: Decimal

    stop_loss: Decimal | None = None

    take_profit: Decimal | None = None

    floating_profit: Decimal = Decimal("0")

    swap: Decimal = Decimal("0")

    commission: Decimal = Decimal("0")

    risk_reward_ratio: Decimal | None = None

    initial_risk: Decimal | None = None

    status: PositionStatus = PositionStatus.OPEN

    opened_at: datetime

    closed_at: datetime | None = None

    last_updated_price_at: datetime | None = None

    break_even_enabled: bool = False

    trailing_stop_enabled: bool = False

    comment: str | None = Field(
        default=None,
        max_length=255,
    )


# ==========================================================
# Create Schema
# ==========================================================

class PositionCreate(PositionBase):
    """
    Payload used when creating a position.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class PositionUpdate(BaseModel):
    """
    Payload used when updating a position.
    """

    broker_position_id: str | None = Field(
        default=None,
        max_length=100,
    )

    strategy: str | None = Field(
        default=None,
        max_length=100,
    )

    direction: PositionDirection | None = None

    volume: Decimal | None = None

    current_volume: Decimal | None = None

    current_price: Decimal | None = None

    stop_loss: Decimal | None = None

    take_profit: Decimal | None = None

    floating_profit: Decimal | None = None

    swap: Decimal | None = None

    commission: Decimal | None = None

    risk_reward_ratio: Decimal | None = None

    initial_risk: Decimal | None = None

    status: PositionStatus | None = None

    closed_at: datetime | None = None

    last_updated_price_at: datetime | None = None

    break_even_enabled: bool | None = None

    trailing_stop_enabled: bool | None = None

    comment: str | None = Field(
        default=None,
        max_length=255,
    )


# ==========================================================
# Response Schema
# ==========================================================

class PositionResponse(PositionBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    created_at: datetime

    updated_at: datetime