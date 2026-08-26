from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.market.candles import Candle
from engine.strategy.manager import StrategyManager
from engine.strategy.registry import StrategyRegistry
from engine.strategy.signals import Signal, SignalSide
from engine.core.trading_loop import AutonomousPaperTrader


class FixedSignalStrategy:
    name = "fixed"

    def __init__(self, signal):
        self.signal = signal

    def on_candle(self, candle):
        return self.signal


def make_trader(signal):
    registry = StrategyRegistry()
    registry.register(FixedSignalStrategy(signal))
    return AutonomousPaperTrader(StrategyManager(registry))


def make_candle():
    now = datetime.now(timezone.utc)
    return Candle("EURUSD", "M1", Decimal("99"), Decimal("101"), Decimal("98"), Decimal("100"), Decimal("10"), now)


def test_approved_signal_is_sized_and_filled():
    trader = make_trader(
        Signal("EURUSD", SignalSide.BUY, entry=Decimal("100"), stop_loss=Decimal("95"))
    )

    attempts = trader.on_candle(make_candle())

    assert attempts[0].approved is True
    assert attempts[0].reason == "filled"
    assert attempts[0].volume == Decimal("2.00")
    assert len(trader.execution.broker.adapter.orders) == 1


def test_signal_without_stop_is_rejected_without_order():
    trader = make_trader(Signal("EURUSD", SignalSide.BUY, entry=Decimal("100")))

    attempts = trader.on_candle(make_candle())

    assert attempts[0].approved is False
    assert attempts[0].reason == "stop loss is required"
    assert trader.execution.broker.adapter.orders == []


def test_risk_rejection_does_not_reach_broker():
    trader = make_trader(
        Signal("EURUSD", SignalSide.BUY, entry=Decimal("100"), stop_loss=Decimal("95"))
    )
    trader.risk.max_risk_percent = Decimal("0.5")

    attempts = trader.on_candle(make_candle())

    assert attempts[0].approved is False
    assert "exceeds maximum" in attempts[0].reason
    assert trader.execution.broker.adapter.orders == []