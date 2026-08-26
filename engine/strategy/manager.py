"""Strategy manager."""

from engine.market.candles import Candle
from engine.strategy.registry import StrategyRegistry
from engine.strategy.signals import Signal


class StrategyManager:
    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self.registry = registry or StrategyRegistry()

    def on_candle(self, candle: Candle) -> list[Signal]:
        signals: list[Signal] = []
        for name in self.registry.names():
            signal = self.registry.get(name).on_candle(candle)
            if signal is not None:
                signals.append(signal)
        return signals
