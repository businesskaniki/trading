"""Broker manager that owns the selected adapter."""

from engine.broker.base import BrokerAdapter, BrokerOrderRequest, BrokerOrderResult
from engine.broker.paper import PaperBroker


class BrokerManager:
    def __init__(self, adapter: BrokerAdapter | None = None) -> None:
        self.adapter = adapter or PaperBroker()

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        return self.adapter.place_order(request)
