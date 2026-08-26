"""Simple moving-average cross strategy example."""

from decimal import Decimal

from engine.market.candles import Candle
from engine.strategy.signals import Signal, SignalSide


class EmaCross:
    name = "ema_cross"

    def __init__(self) -> None:
        self.previous_close: Decimal | None = None

    def on_candle(self, candle: Candle) -> Signal | None:
        if self.previous_close is None:
            self.previous_close = candle.close
            return None
        side = SignalSide.BUY if candle.close > self.previous_close else SignalSide.SELL
        self.previous_close = candle.close
        return Signal(symbol=candle.symbol, side=side, entry=candle.close)
