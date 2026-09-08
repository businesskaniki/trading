from __future__ import annotations

from dataclasses import dataclass

from app.market_data.models import MarketCandle, MarketTick

from .base import Event


@dataclass(frozen=True, slots=True)
class MarketTickEvent(Event):
    """
    Published whenever a new market tick is received.

    The event contains the normalized MarketTick object so that
    downstream consumers do not need to know where the data came from.
    """

    tick: MarketTick

    @property
    def symbol(self) -> str:
        return self.tick.symbol


@dataclass(frozen=True, slots=True)
class MarketCandleEvent(Event):
    """
    Published when a normalized market candle is available.
    """

    candle: MarketCandle

    @property
    def symbol(self) -> str:
        return self.candle.symbol

    @property
    def timeframe(self) -> str:
        return self.candle.timeframe
