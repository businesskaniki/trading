"""Tradable symbol metadata."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    tick_size: Decimal
    contract_size: Decimal
    min_volume: Decimal = Decimal("0.01")
    max_volume: Decimal = Decimal("100")
    volume_step: Decimal = Decimal("0.01")

    @property
    def tick_value(self) -> Decimal:
        return self.tick_size * self.contract_size
