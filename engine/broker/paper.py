"""Deterministic in-memory paper broker."""

from decimal import Decimal
from uuid import uuid4

from engine.broker.base import BrokerOrderRequest, BrokerOrderResult


class PaperBroker:
    def __init__(self, equity: Decimal = Decimal("100000")) -> None:
        self._equity = equity
        self.orders: list[BrokerOrderResult] = []

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        fill_price = request.price or Decimal("0")
        result = BrokerOrderResult(
            order_id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            fill_price=fill_price,
            status="filled",
        )
        self.orders.append(result)
        return result

    def account_equity(self) -> Decimal:
        return self._equity
