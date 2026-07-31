from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict

from app.core.constants import RiskLevel


# ==========================================================
# Base Schema
# ==========================================================

class RiskSnapshotBase(BaseModel):
    """
    Shared Risk Snapshot fields.
    """

    account_id: UUID

    # ======================================================
    # Account Snapshot
    # ======================================================

    balance: Decimal

    equity: Decimal

    margin: Decimal

    free_margin: Decimal

    margin_level: Decimal

    # ======================================================
    # Exposure
    # ======================================================

    total_open_positions: int = 0

    total_open_orders: int = 0

    total_volume: Decimal = Decimal("0")

    exposure: Decimal = Decimal("0")

    exposure_percent: Decimal = Decimal("0")

    # ======================================================
    # Drawdown
    # ======================================================

    floating_profit_loss: Decimal = Decimal("0")

    daily_drawdown: Decimal = Decimal("0")

    daily_drawdown_percent: Decimal = Decimal("0")

    max_drawdown: Decimal = Decimal("0")

    max_drawdown_percent: Decimal = Decimal("0")

    # ======================================================
    # Risk Metrics
    # ======================================================

    value_at_risk: Decimal | None = None

    expected_shortfall: Decimal | None = None

    portfolio_heat: Decimal = Decimal("0")

    risk_per_trade: Decimal = Decimal("0")

    total_open_risk: Decimal = Decimal("0")

    correlation_risk: Decimal = Decimal("0")

    # ======================================================
    # Risk Status
    # ======================================================

    risk_level: RiskLevel

    daily_loss_limit_hit: bool = False

    weekly_loss_limit_hit: bool = False

    trading_halted: bool = False

    # ======================================================
    # Timestamp
    # ======================================================

    snapshot_time: datetime


# ==========================================================
# Create Schema
# ==========================================================

class RiskSnapshotCreate(RiskSnapshotBase):
    """
    Payload used when creating a risk snapshot.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class RiskSnapshotUpdate(BaseModel):
    """
    Payload used when updating a risk snapshot.
    """

    balance: Decimal | None = None
    equity: Decimal | None = None
    margin: Decimal | None = None
    free_margin: Decimal | None = None
    margin_level: Decimal | None = None

    total_open_positions: int | None = None
    total_open_orders: int | None = None
    total_volume: Decimal | None = None
    exposure: Decimal | None = None
    exposure_percent: Decimal | None = None

    floating_profit_loss: Decimal | None = None
    daily_drawdown: Decimal | None = None
    daily_drawdown_percent: Decimal | None = None
    max_drawdown: Decimal | None = None
    max_drawdown_percent: Decimal | None = None

    value_at_risk: Decimal | None = None
    expected_shortfall: Decimal | None = None
    portfolio_heat: Decimal | None = None
    risk_per_trade: Decimal | None = None
    total_open_risk: Decimal | None = None
    correlation_risk: Decimal | None = None

    risk_level: RiskLevel | None = None

    daily_loss_limit_hit: bool | None = None
    weekly_loss_limit_hit: bool | None = None
    trading_halted: bool | None = None

    snapshot_time: datetime | None = None


# ==========================================================
# Response Schema
# ==========================================================

class RiskSnapshotResponse(RiskSnapshotBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    created_at: datetime

    updated_at: datetime