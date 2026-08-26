"""Service wrapper around the execution engine."""

from engine.execution.engine import ExecutionEngine
from engine.execution.orders import Order


class Executor:
    def __init__(self, engine: ExecutionEngine | None = None) -> None:
        self.engine = engine or ExecutionEngine()

    def submit(self, order: Order):
        return self.engine.execute(order)
