"""Portfolio account state."""

from dataclasses import dataclass, field
from decimal import Decimal

from engine.portfolio.positions import Position


@dataclass
class Account:
    balance: Decimal
    positions: list[Position] = field(default_factory=list)

    @property
    def equity(self) -> Decimal:
        return self.balance + sum((p.unrealized_pnl for p in self.positions), Decimal("0"))
