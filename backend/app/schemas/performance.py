from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.core.constants import PerformancePeriod


# ==========================================================
# Base Schema
# ==========================================================

class PerformanceBase(BaseModel):
    """
    Shared Performance fields.
    """

    strategy_run_id: UUID

    period: PerformancePeriod

    generated_at: datetime

    # ======================================================
    # Trade Statistics
    # ======================================================

    total_trades: int = 0

    winning_trades: int = 0

    losing_trades: int = 0

    breakeven_trades: int = 0

    # ======================================================
    # Financial Metrics
    # ======================================================

    gross_profit: Decimal = Decimal("0")

    gross_loss: Decimal = Decimal("0")

    net_profit: Decimal = Decimal("0")

    total_commission: Decimal = Decimal("0")

    total_swap: Decimal = Decimal("0")

    total_fees: Decimal = Decimal("0")

    # ======================================================
    # Performance Ratios
    # ======================================================

    win_rate: Decimal = Decimal("0")

    profit_factor: Decimal = Decimal("0")

    expectancy: Decimal = Decimal("0")

    sharpe_ratio: Decimal | None = None

    sortino_ratio: Decimal | None = None

    calmar_ratio: Decimal | None = None

    # ======================================================
    # Drawdown
    # ======================================================

    max_drawdown: Decimal = Decimal("0")

    max_drawdown_percent: Decimal = Decimal("0")

    # ======================================================
    # Risk Metrics
    # ======================================================

    average_r_multiple: Decimal | None = None

    recovery_factor: Decimal | None = None

    payoff_ratio: Decimal | None = None

    # ======================================================
    # Holding Statistics
    # ======================================================

    average_trade_duration_seconds: int = 0

    average_win: Decimal = Decimal("0")

    average_loss: Decimal = Decimal("0")

    largest_win: Decimal = Decimal("0")

    largest_loss: Decimal = Decimal("0")

    # ======================================================
    # Equity
    # ======================================================

    starting_balance: Decimal

    ending_balance: Decimal

    peak_equity: Decimal

    lowest_equity: Decimal


# ==========================================================
# Create Schema
# ==========================================================

class PerformanceCreate(PerformanceBase):
    """
    Payload used when creating performance statistics.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class PerformanceUpdate(BaseModel):
    """
    Payload used when updating performance statistics.
    """

    period: PerformancePeriod | None = None

    generated_at: datetime | None = None

    total_trades: int | None = None
    winning_trades: int | None = None
    losing_trades: int | None = None
    breakeven_trades: int | None = None

    gross_profit: Decimal | None = None
    gross_loss: Decimal | None = None
    net_profit: Decimal | None = None

    total_commission: Decimal | None = None
    total_swap: Decimal | None = None
    total_fees: Decimal | None = None

    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    expectancy: Decimal | None = None

    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None

    max_drawdown: Decimal | None = None
    max_drawdown_percent: Decimal | None = None

    average_r_multiple: Decimal | None = None
    recovery_factor: Decimal | None = None
    payoff_ratio: Decimal | None = None

    average_trade_duration_seconds: int | None = None

    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    largest_win: Decimal | None = None
    largest_loss: Decimal | None = None

    starting_balance: Decimal | None = None
    ending_balance: Decimal | None = None
    peak_equity: Decimal | None = None
    lowest_equity: Decimal | None = None


# ==========================================================
# Response Schema
# ==========================================================

class PerformanceResponse(PerformanceBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    created_at: datetime

    updated_at: datetime