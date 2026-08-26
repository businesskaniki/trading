"""Market tick models."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class Tick:
    symbol: str
    bid: Decimal
    ask: Decimal
    time: datetime = datetime.now(timezone.utc)

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")
