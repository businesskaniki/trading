"""Runs registered strategies over candle input."""

from engine.market.candles import Candle
from engine.strategy.manager import StrategyManager


class Runner:
    def __init__(self, manager: StrategyManager | None = None) -> None:
        self.manager = manager or StrategyManager()

    def on_candle(self, candle: Candle):
        return self.manager.on_candle(candle)
