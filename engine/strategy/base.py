"""Base strategy interface."""

from typing import Protocol

from engine.market.candles import Candle
from engine.strategy.signals import Signal


class Strategy(Protocol):
    name: str

    def on_candle(self, candle: Candle) -> Signal | None: ...
