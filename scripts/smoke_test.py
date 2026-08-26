"""Local smoke checks for the Athena Quant Engine workspace.

The smoke test intentionally avoids external services. It verifies that the
backend app imports with development environment variables, and that the engine
can publish events, calculate risk sizing, route a paper order, dispatch a
strategy signal, and calculate portfolio/analytics values.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _ensure_backend_env() -> None:
    defaults = {
        "SECRET_KEY": "local-smoke-secret",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "athena",
        "POSTGRES_USER": "athena",
        "POSTGRES_PASSWORD": "athena",
        "REDIS_HOST": "localhost",
        "SMTP_HOST": "localhost",
        "SMTP_USERNAME": "smoke",
        "SMTP_PASSWORD": "smoke",
        "SMTP_FROM_EMAIL": "smoke@example.com",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def check_backend_import() -> None:
    _ensure_backend_env()
    from app.main import app

    assert app.title == "Athena Quant Engine"


def check_engine_flow() -> None:
    from engine.analytics.metrics import profit_factor, win_rate
    from engine.broker.base import OrderSide
    from engine.events.bus import Event, EventBus
    from engine.execution.engine import ExecutionEngine
    from engine.execution.orders import Order
    from engine.market.candles import Candle
    from engine.portfolio.account import Account
    from engine.portfolio.positions import Position
    from engine.risk.position_sizer import position_size
    from engine.strategy.manager import StrategyManager
    from engine.strategy.registry import StrategyRegistry
    from strategies.trend.ema_cross import EmaCross

    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("smoke", seen.append)
    assert bus.publish(Event(type="smoke", payload={"ok": True})) == 1
    assert seen[0].payload == {"ok": True}

    volume = position_size(
        equity=Decimal("100000"),
        risk_percent=Decimal("1"),
        entry=Decimal("100"),
        stop=Decimal("95"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1"),
        volume_step=Decimal("0.01"),
    )
    assert volume == Decimal("2.00")

    execution = ExecutionEngine()
    result = execution.execute(
        Order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            volume=Decimal("0.01"),
            price=Decimal("1.1000"),
        )
    )
    assert result.status == "filled"

    registry = StrategyRegistry()
    registry.register(EmaCross())
    manager = StrategyManager(registry)
    first = Candle("EURUSD", "M1", Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1.1"), Decimal("10"), datetime.now(timezone.utc))
    second = Candle("EURUSD", "M1", Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1.2"), Decimal("10"), datetime.now(timezone.utc))
    assert manager.on_candle(first) == []
    signals = manager.on_candle(second)
    assert len(signals) == 1
    assert signals[0].symbol == "EURUSD"

    account = Account(
        balance=Decimal("1000"),
        positions=[Position("EURUSD", Decimal("2"), Decimal("10"), Decimal("12"))],
    )
    assert account.equity == Decimal("1004")
    assert win_rate([Decimal("1"), Decimal("-1"), Decimal("2")]) == Decimal("66.66666666666666666666666667")
    assert profit_factor([Decimal("3"), Decimal("-1")]) == Decimal("3")


def main() -> None:
    check_backend_import()
    check_engine_flow()
    print("smoke checks passed")


if __name__ == "__main__":
    main()
