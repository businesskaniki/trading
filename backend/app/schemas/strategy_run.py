from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType


# ==========================================================
# Base Schema
# ==========================================================

class StrategyRunBase(BaseModel):
    """
    Shared Strategy Run fields.
    """

    # ======================================================
    # Strategy Information
    # ======================================================

    strategy_name: str

    strategy_version: str

    run_name: str

    description: str | None = None

    # ======================================================
    # Execution
    # ======================================================

    run_type: StrategyRunType

    status: StrategyRunStatus = StrategyRunStatus.CREATED

    # ======================================================
    # Configuration
    # ======================================================

    parameters: dict = {}

    symbols: list[str] = []

    timeframe: str

    # ======================================================
    # Statistics
    # ======================================================

    total_trades: int = 0

    winning_trades: int = 0

    losing_trades: int = 0

    net_profit: Decimal = Decimal("0")

    max_drawdown: Decimal = Decimal("0")

    profit_factor: Decimal | None = None

    sharpe_ratio: Decimal | None = None

    expectancy: Decimal | None = None

    # ======================================================
    # Timing
    # ======================================================

    started_at: datetime

    ended_at: datetime | None = None

    # ======================================================
    # Notes
    # ======================================================

    notes: str | None = None


# ==========================================================
# Create Schema
# ==========================================================

class StrategyRunCreate(StrategyRunBase):
    """
    Payload used when creating a strategy run.
    """

    pass


# ==========================================================
# Update Schema
# ==========================================================

class StrategyRunUpdate(BaseModel):
    """
    Payload used when updating a strategy run.
    """

    strategy_name: str | None = None

    strategy_version: str | None = None

    run_name: str | None = None

    description: str | None = None

    run_type: StrategyRunType | None = None

    status: StrategyRunStatus | None = None

    parameters: dict | None = None

    symbols: list[str] | None = None

    timeframe: str | None = None

    total_trades: int | None = None

    winning_trades: int | None = None

    losing_trades: int | None = None

    net_profit: Decimal | None = None

    max_drawdown: Decimal | None = None

    profit_factor: Decimal | None = None

    sharpe_ratio: Decimal | None = None

    expectancy: Decimal | None = None

    started_at: datetime | None = None

    ended_at: datetime | None = None

    notes: str | None = None


# ==========================================================
# Response Schema
# ==========================================================

class StrategyRunResponse(StrategyRunBase):
    """
    Returned to API clients.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    created_at: datetime

    updated_at: datetime