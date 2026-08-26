from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import StrategyRunStatus


class BotStartRequest(BaseModel):
    strategy_name: str = Field(min_length=1, max_length=100)
    strategy_version: str = Field(default="1.0.0", max_length=30)
    symbols: list[str] = Field(min_length=1)
    timeframe: str = Field(default="M1", min_length=2, max_length=10)
    account_id: UUID | None = None
    risk_percent: Decimal = Field(default=Decimal("1"), gt=0, le=2)


class BotStatusResponse(BaseModel):
    active: bool
    status: StrategyRunStatus | None = None
    run_id: UUID | None = None
    strategy_name: str | None = None
    symbols: list[str] = Field(default_factory=list)
    timeframe: str | None = None
    account_id: UUID | None = None
    risk_percent: Decimal | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None