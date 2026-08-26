"""Order execution engine."""

from engine.broker.base import BrokerOrderRequest, BrokerOrderResult
from engine.broker.manager import BrokerManager
from engine.execution.orders import Order


class ExecutionEngine:
    def __init__(self, broker: BrokerManager | None = None) -> None:
        self.broker = broker or BrokerManager()

    def execute(self, order: Order) -> BrokerOrderResult:
        request = BrokerOrderRequest(symbol=order.symbol, side=order.side, volume=order.volume, price=order.price)
        return self.broker.place_order(request)
