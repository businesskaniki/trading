from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ==========================================================
# RISK PROFILE
# ==========================================================


class RiskProfileCreate(BaseModel):
    """
    Schema used when creating a risk profile.
    """

    account_id: UUID

    enabled: bool = True

    min_risk_percent: Decimal = Field(
        default=Decimal("0.25"),
        gt=0,
    )

    base_risk_percent: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
    )

    max_risk_percent: Decimal = Field(
        default=Decimal("2.00"),
        gt=0,
    )

    risk_multiplier: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
    )

    max_daily_loss_percent: Decimal = Field(
        default=Decimal("5.00"),
        gt=0,
    )

    max_drawdown_percent: Decimal = Field(
        default=Decimal("10.00"),
        gt=0,
    )

    max_open_risk_percent: Decimal = Field(
        default=Decimal("6.00"),
        gt=0,
    )

    max_open_positions: int | None = Field(
        default=10,
        ge=1,
    )

    max_symbol_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_strategy_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )


class RiskProfileUpdate(BaseModel):
    """
    Schema used when updating a risk profile.

    All fields are optional so partial updates are supported.
    """

    enabled: bool | None = None

    min_risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    base_risk_percent: Decimal | None = Field(
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

    max_open_positions: int | None = Field(
        default=None,
        ge=1,
    )

    max_symbol_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )

    max_strategy_exposure_percent: Decimal | None = Field(
        default=None,
        gt=0,
    )


class RiskProfileResponse(BaseModel):
    """
    Risk profile returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    account_id: UUID

    enabled: bool

    min_risk_percent: Decimal
    base_risk_percent: Decimal
    max_risk_percent: Decimal

    risk_multiplier: Decimal

    max_daily_loss_percent: Decimal
    max_drawdown_percent: Decimal
    max_open_risk_percent: Decimal

    max_open_positions: int | None

    max_symbol_exposure_percent: Decimal | None
    max_strategy_exposure_percent: Decimal | None

    created_at: datetime
    updated_at: datetime


# ==========================================================
# POSITION SIZING REQUEST
# ==========================================================


class RiskSizingRequest(BaseModel):
    """
    Request for risk-based position sizing.

    Account equity, tick size, tick value and volume step
    are obtained server-side by RiskService.

    The client should therefore NOT be trusted to provide
    account financial state or instrument metadata.
    """

    account_id: UUID
    symbol_id: UUID

    entry_price: Decimal = Field(
        gt=0,
    )

    stop_loss_price: Decimal = Field(
        gt=0,
    )


# ==========================================================
# POSITION SIZING RESPONSE
# ==========================================================


class RiskSizingResponse(BaseModel):
    """
    Result of a risk-based position-size calculation.
    """

    account_id: UUID
    symbol_id: UUID

    risk_percent: Decimal
    risk_multiplier: Decimal

    equity: Decimal
    risk_amount: Decimal

    entry_price: Decimal
    stop_loss_price: Decimal
    stop_distance: Decimal

    tick_size: Decimal
    tick_value: Decimal

    risk_per_unit: Decimal

    raw_volume: Decimal
    recommended_volume: Decimal

    volume_step: Decimal

    minimum_volume: Decimal
    maximum_volume: Decimal


# ==========================================================
# RISK CHECK REQUEST
# ==========================================================


class RiskCheckRequest(BaseModel):
    """
    Request to evaluate whether a proposed trade is allowed.

    Server-side state is used by RiskService. The client does
    not provide current account risk state.
    """

    account_id: UUID
    symbol_id: UUID

    proposed_risk_amount: Decimal = Field(
        gt=0,
    )

    proposed_symbol_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    proposed_strategy_exposure_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    strategy: str | None = None


# ==========================================================
# RISK CHECK RESPONSE
# ==========================================================


class RiskCheckResponse(BaseModel):
    """
    Structured result of a complete risk evaluation.
    """

    account_id: UUID
    symbol_id: UUID

    approved: bool

    code: str
    message: str

    risk_percent: Decimal
    proposed_risk_amount: Decimal

    current_open_risk: Decimal
    projected_open_risk: Decimal

    current_open_positions: int
    projected_open_positions: int

    trading_halted: bool

    metadata: dict[str, object] = Field(
        default_factory=dict,
    )


# ==========================================================
# RISK STATE RESPONSE
# ==========================================================


class RiskStateResponse(BaseModel):
    """
    Server-side risk state exposed for monitoring.
    """

    account_id: UUID

    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal

    open_positions: int
    open_orders: int

    total_volume: Decimal
    exposure: Decimal
    exposure_percent: Decimal

    floating_profit_loss: Decimal

    daily_loss_amount: Decimal
    daily_loss_percent: Decimal

    drawdown_amount: Decimal
    drawdown_percent: Decimal

    total_open_risk: Decimal
    portfolio_heat: Decimal

    trading_halted: bool

    generated_at: datetime


# ==========================================================
# RISK DECISION RESPONSE
# ==========================================================


class RiskDecisionResponse(BaseModel):
    """
    Public API representation of a RiskDecision.
    """

    approved: bool

    code: str

    message: str

    metadata: dict[str, object] = Field(
        default_factory=dict,
    )


# ==========================================================
# RISK SNAPSHOT RESPONSE
# ==========================================================


class RiskSnapshotResponse(BaseModel):
    """
    Historical risk snapshot.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    account_id: UUID

    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal

    total_open_positions: int
    total_open_orders: int

    total_volume: Decimal

    exposure: Decimal
    exposure_percent: Decimal

    floating_profit_loss: Decimal

    daily_drawdown: Decimal
    daily_drawdown_percent: Decimal

    max_drawdown: Decimal
    max_drawdown_percent: Decimal

    value_at_risk: Decimal | None
    expected_shortfall: Decimal | None

    portfolio_heat: Decimal
    risk_per_trade: Decimal
    total_open_risk: Decimal
    correlation_risk: Decimal

    risk_level: str

    daily_loss_limit_hit: bool
    weekly_loss_limit_hit: bool
    trading_halted: bool

    snapshot_time: datetime

    created_at: datetime
    updated_at: datetime
