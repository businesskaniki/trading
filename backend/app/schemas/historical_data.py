from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HistoricalCandleResponse(BaseModel):
    """
    API representation of a persisted historical candle.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol_id: UUID
    timeframe: str
    timestamp: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    volume: Decimal
    spread: Decimal | None = None


class HistoricalCandleListResponse(BaseModel):
    """
    Response containing persisted historical candles.
    """

    symbol_id: UUID
    timeframe: str
    count: int
    candles: list[HistoricalCandleResponse]


class HistoricalDataSyncRequest(BaseModel):
    """
    Request to synchronize historical candles for all enabled
    symbols belonging to a trading account.
    """

    timeframe: str = Field(
        default="M15",
        min_length=1,
        max_length=10,
    )

    count: int = Field(
        default=200,
        ge=1,
        le=10000,
    )


class HistoricalDataSyncSymbolResult(BaseModel):
    """
    Synchronization result for one selected trading symbol.
    """

    status: str
    symbol_id: UUID
    symbol: str
    broker_symbol: str
    timeframe: str

    requested: int
    received: int
    inserted: int

    error: str | None = None


class HistoricalDataSyncResponse(BaseModel):
    """
    Complete historical-data synchronization result.
    """

    account_id: UUID
    timeframe: str
    requested_count: int

    symbols_selected: int
    symbols_synchronized: int
    symbols_failed: int

    results: list[HistoricalDataSyncSymbolResult]
