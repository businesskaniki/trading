from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    PositionDirection,
    PositionStatus,
)

# ==========================================================
# CREATE SCHEMA
# ==========================================================


class PositionCreate(BaseModel):
    """
    Data required to create an AQE Position from broker/execution state.

    Broker-generated values such as ticket, prices, status, and
    timestamps are supplied by the position synchronization layer.
    """

    ticket: int = Field(
        ...,
        gt=0,
    )

    broker_position_id: str | None = Field(
        default=None,
        max_length=100,
    )

    strategy: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    account_id: UUID

    symbol_id: UUID

    order_id: UUID

    direction: PositionDirection

    volume: Decimal = Field(
        ...,
        gt=0,
    )

    current_volume: Decimal | None = Field(
        default=None,
        ge=0,
    )

    entry_price: Decimal = Field(
        ...,
        gt=0,
    )

    current_price: Decimal = Field(
        ...,
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

    floating_profit: Decimal = Decimal("0")

    swap: Decimal = Decimal("0")

    commission: Decimal = Decimal("0")

    risk_reward_ratio: Decimal | None = Field(
        default=None,
        gt=0,
    )

    initial_risk: Decimal | None = Field(
        default=None,
        ge=0,
    )

    opened_at: datetime

    last_updated_price_at: datetime | None = None

    break_even_enabled: bool = False

    trailing_stop_enabled: bool = False

    comment: str | None = Field(
        default=None,
        max_length=255,
    )

    @model_validator(mode="after")
    def validate_volume(self):
        if self.current_volume > self.volume:
            raise ValueError("current_volume cannot be greater than volume.")

        return self


# ==========================================================
# UPDATE SCHEMA
# ==========================================================


class PositionUpdate(BaseModel):
    """
    Fields that may change during the position lifecycle.
    """

    broker_position_id: str | None = Field(
        default=None,
        max_length=100,
    )

    strategy: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    direction: PositionDirection | None = None

    volume: Decimal | None = Field(
        default=None,
        gt=0,
    )

    current_volume: Decimal | None = Field(
        default=None,
        ge=0,
    )

    current_price: Decimal | None = Field(
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

    floating_profit: Decimal | None = None

    swap: Decimal | None = None

    commission: Decimal | None = None

    risk_reward_ratio: Decimal | None = Field(
        default=None,
        gt=0,
    )

    initial_risk: Decimal | None = Field(
        default=None,
        ge=0,
    )

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
# RESPONSE SCHEMA
# ==========================================================


class PositionResponse(BaseModel):
    """
    Position representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    ticket: int

    broker_position_id: str | None

    strategy: str

    account_id: UUID

    symbol_id: UUID

    order_id: UUID

    direction: PositionDirection

    volume: Decimal

    current_volume: Decimal

    entry_price: Decimal

    current_price: Decimal

    stop_loss: Decimal | None

    take_profit: Decimal | None

    floating_profit: Decimal

    swap: Decimal

    commission: Decimal

    risk_reward_ratio: Decimal | None

    initial_risk: Decimal | None

    status: PositionStatus

    opened_at: datetime

    closed_at: datetime | None

    last_updated_price_at: datetime | None

    break_even_enabled: bool

    trailing_stop_enabled: bool

    comment: str | None

    created_at: datetime

    updated_at: datetime
