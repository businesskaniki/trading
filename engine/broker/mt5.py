"""External broker adapter placeholder with explicit unsupported behavior."""

from decimal import Decimal

from engine.broker.base import BrokerOrderRequest, BrokerOrderResult


class ExternalBrokerUnavailable(RuntimeError):
    """Raised when a live broker adapter is not configured."""


class Broker:
    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        raise ExternalBrokerUnavailable("Live broker adapter is not configured")

    def account_equity(self) -> Decimal:
        raise ExternalBrokerUnavailable("Live broker adapter is not configured")
