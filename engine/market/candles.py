"""Candle aggregation primitives."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    opened_at: datetime

    @property
    def range(self) -> Decimal:
        return self.high - self.low
