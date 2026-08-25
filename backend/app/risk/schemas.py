from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class RiskProfileCreate(BaseModel):
    """
    Create the risk configuration for a trading account.
    """

    account_id: UUID

    enabled: bool = True

    base_risk_percent: Decimal = Field(
        default=Decimal("1.0000"),
        gt=0,
    )

    min_risk_percent: Decimal = Field(
        default=Decimal("0.2500"),
        gt=0,
    )

    max_risk_percent: Decimal = Field(
        default=Decimal("2.0000"),
        gt=0,
    )

    risk_multiplier: Decimal = Field(
        default=Decimal("1.0000"),
        gt=0,
    )

    max_daily_loss_percent: Decimal = Field(
        default=Decimal("3.0000"),
        gt=0,
    )

    max_drawdown_percent: Decimal = Field(
        default=Decimal("10.0000"),
        gt=0,
    )

    max_open_risk_percent: Decimal = Field(
        default=Decimal("5.0000"),
        gt=0,
    )

    max_positions: int = Field(
        default=10,
        gt=0,
    )

    max_symbol_exposure_percent: Decimal = Field(
        default=Decimal("5.0000"),
        gt=0,
    )

    max_strategy_exposure_percent: Decimal = Field(
        default=Decimal("5.0000"),
        gt=0,
    )

    hard_limits_enabled: bool = True


class RiskProfileUpdate(BaseModel):
    """
    Update the account's risk configuration.
    """

    enabled: bool | None = None

    base_risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    min_risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    risk_multiplier: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_daily_loss_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_drawdown_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_open_risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_positions: int | None = Field(
        default=None,
        gt=0,
    )

    max_symbol_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_strategy_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    hard_limits_enabled: bool | None = None


class RiskProfileResponse(BaseModel):
    """
    Risk configuration returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    account_id: UUID

    enabled: bool

    base_risk_percent: Decimal
    min_risk_percent: Decimal
    max_risk_percent: Decimal

    risk_multiplier: Decimal

    max_daily_loss_percent: Decimal
    max_drawdown_percent: Decimal
    max_open_risk_percent: Decimal

    max_positions: int

    max_symbol_exposure_percent: Decimal
    max_strategy_exposure_percent: Decimal

    hard_limits_enabled: bool


class RiskSizingRequest(BaseModel):
    """
    Input required to calculate position size from risk.
    """

    account_id: UUID

    entry_price: Decimal = Field(
        ...,
        gt=0,
    )

    stop_loss_price: Decimal = Field(
        ...,
        gt=0,
    )

    tick_size: Decimal = Field(
        ...,
        gt=0,
    )

    tick_value: Decimal = Field(
        ...,
        gt=0,
    )

    strategy: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )


class RiskSizingResponse(BaseModel):
    """
    Result of the risk sizing calculation.
    """

    risk_percent: Decimal
    risk_multiplier: Decimal

    risk_amount: Decimal

    entry_price: Decimal
    stop_loss_price: Decimal

    stop_distance: Decimal

    tick_size: Decimal
    tick_value: Decimal

    raw_volume: Decimal
    recommended_volume: Decimal

    risk_per_unit: Decimal


class RiskCheckRequest(BaseModel):
    """
    Proposed trade risk state used before execution.
    """

    account_id: UUID

    proposed_risk_amount: Decimal = Field(
        ...,
        ge=0,
    )

    proposed_symbol_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    proposed_strategy_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    current_open_risk_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    current_symbol_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    current_strategy_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    current_open_positions: int = Field(
        default=0,
        ge=0,
    )

    account_equity: Decimal = Field(
        ...,
        gt=0,
    )

    daily_loss_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    drawdown_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )


class RiskCheckResponse(BaseModel):
    """
    Result of a risk decision.

    A trade must never be executed when allowed=False.
    """

    allowed: bool

    risk_percent: Decimal

    risk_amount: Decimal

    available_risk_amount: Decimal

    projected_open_risk_percent: Decimal

    projected_symbol_exposure_percent: Decimal

    projected_strategy_exposure_percent: Decimal

    projected_daily_loss_percent: Decimal

    projected_drawdown_percent: Decimal

    projected_positions: int

    reason: str | None = None