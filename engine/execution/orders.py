"""Engine order model."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from engine.broker.base import OrderSide


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderSide
    volume: Decimal
    id: str = ""
    price: Decimal | None = None

    def with_id(self) -> "Order":
        return Order(self.symbol, self.side, self.volume, str(uuid4()), self.price)
