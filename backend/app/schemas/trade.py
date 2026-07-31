from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import PositionDirection, TradeResult


class TradeBase(BaseModel):
    """
    Shared trade fields.
    """

    ticket: int
    strategy: str

    position_id: UUID
    account_id: UUID
    symbol_id: UUID

    direction: PositionDirection

    volume: Decimal

    entry_price: Decimal
    exit_price: Decimal

    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    gross_profit: Decimal

    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")

    net_profit: Decimal
    profit_percent: Decimal | None = None

    initial_risk: Decimal | None = None
    reward_risk_ratio: Decimal | None = None

    max_favorable_excursion: Decimal | None = None
    max_adverse_excursion: Decimal | None = None

    result: TradeResult

    opened_at: datetime
    closed_at: datetime

    duration_seconds: int

    comment: str | None = None



class TradeCreate(TradeBase):
    """
    Schema used internally when a position closes
    and a trade record is created.
    """

    pass



class TradeUpdate(BaseModel):
    """
    Normally unused because trades are immutable.

    Included only if you later allow
    admin corrections.
    """

    comment: str | None = None



class TradeResponse(TradeBase):
    """
    API response schema.
    """

    id: UUID

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )



class TradeListResponse(BaseModel):
    """
    Paginated trade response.
    """

    total: int
    items: list[TradeResponse]