"""Portfolio position tracking."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Position:
    symbol: str
    volume: Decimal
    entry_price: Decimal
    current_price: Decimal

    @property
    def unrealized_pnl(self) -> Decimal:
        return (self.current_price - self.entry_price) * self.volume
