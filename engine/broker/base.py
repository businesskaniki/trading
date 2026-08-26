"""Broker adapter protocol and shared domain models."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class BrokerOrderRequest:
    symbol: str
    side: OrderSide
    volume: Decimal
    price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


@dataclass(frozen=True)
class BrokerOrderResult:
    order_id: str
    symbol: str
    side: OrderSide
    volume: Decimal
    fill_price: Decimal
    status: str


class BrokerAdapter(Protocol):
    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult: ...
    def account_equity(self) -> Decimal: ...
