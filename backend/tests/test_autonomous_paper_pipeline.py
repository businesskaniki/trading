"""Integration test for AQE's event-driven autonomous PAPER signal path.

This test deliberately avoids Redis, PostgreSQL, and a real broker. It starts
at canonical MarketTickEvent delivery and verifies that completed candle data
can reach an active strategy, that the strategy publishes a signal, and that
an approved decision is handed to the execution boundary.

Place this file at backend/tests/test_autonomous_paper_pipeline.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import inspect
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.events import EventBus
from app.events.market import MarketCandleEvent, MarketTickEvent
from app.events.strategy import StrategySignalEvent
from app.market_data.candle_builder import LiveCandleBuilder
from app.market_data.models import MarketTick
from execution.signal_pipeline import SignalRiskExecutionPipeline
from strategies.core import StrategyConfig
from strategies.core.base import BaseStrategy, StrategyDefinition
from strategies.core.enums import SignalDirection, StrategyMode
from strategies.core.registry import register_strategy
from strategies.core.signal import TradingSignal
from strategies.runtime.dispatcher import StrategyDispatcher
from strategies.runtime.manager import StrategyManager
from strategies.runtime.signal_publisher import StrategySignalPublisher


_TEST_STRATEGY_NAME = "aqe_autonomous_paper_pipeline_test"


@register_strategy(_TEST_STRATEGY_NAME)
class _AutonomousPaperSignalStrategy(BaseStrategy):
    """Deterministic test strategy: emit one LONG signal per M1 candle."""

    # StrategyRegistry requires static implementation metadata on every
    # concrete strategy class before it can be registered.
    definition = StrategyDefinition(
        name=_TEST_STRATEGY_NAME,
        version="1.0.0",
        description="Test-only strategy for the autonomous PAPER pipeline.",
        author="AQE tests",
        tags=["test", "paper-pipeline"],
    )

    async def on_tick(self, event: MarketTickEvent) -> None:
        return None

    async def on_candle(
        self,
        candle: Any,
    ) -> TradingSignal:
        # BaseStrategy.handle_candle unwraps MarketCandleEvent before calling
        # the strategy, so on_candle receives the MarketCandle itself.
        entry = Decimal(str(candle.close))

        # The pipeline test uses a model-constructed TradingSignal so it does
        # not depend on every optional metadata field in the production
        # signal schema. Required identity/routing fields are still supplied.
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "signal_id": str(uuid4()),
            "id": str(uuid4()),
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "direction": SignalDirection.LONG,
            "side": SignalDirection.LONG,
            "confidence": Decimal("0.90"),
            "entry_price": entry,
            "price": entry,
            "stop_loss": entry - Decimal("1.00"),
            "take_profit": entry + Decimal("2.00"),
            "order_type": "MARKET",
            "timestamp": now,
            "created_at": now,
            "occurred_at": now,
            "reason": "Deterministic integration-test signal",
            "metadata": {"test_only": True},
        }

        # Support either a Pydantic signal model or a dataclass-style signal
        # contract. Prefer the production model's declared fields whenever
        # the Pydantic v2 API is available.
        model_fields = getattr(TradingSignal, "model_fields", None)
        model_construct = getattr(TradingSignal, "model_construct", None)
        if model_fields is not None and callable(model_construct):
            valid_values = {
                name: value
                for name, value in values.items()
                if name in model_fields
            }
            return model_construct(**valid_values)

        accepted = set(inspect.signature(TradingSignal).parameters)
        valid_values = {
            name: value
            for name, value in values.items()
            if name in accepted
        }
        return TradingSignal(**valid_values)


class _FakeRiskContextProvider:
    """Stand-in for the database/broker-backed live risk-context provider."""

    async def _make_context(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        signal = kwargs.get("signal")
        if signal is None and args:
            signal = args[0]
        return SimpleNamespace(signal=signal)

    # Common provider method names are provided so the test only stubs the
    # external context-building boundary, not SignalRiskExecutionPipeline.
    async def build(self, signal: TradingSignal) -> SimpleNamespace:
        return await self._make_context(signal)

    async def build_context(self, signal: TradingSignal) -> SimpleNamespace:
        return await self._make_context(signal)

    async def get_context(self, signal: TradingSignal) -> SimpleNamespace:
        return await self._make_context(signal)

    async def create_context(self, signal: TradingSignal) -> SimpleNamespace:
        return await self._make_context(signal)

    async def provide(self, signal: TradingSignal) -> SimpleNamespace:
        return await self._make_context(signal)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        async def fallback(*args: Any, **kwargs: Any) -> SimpleNamespace:
            return await self._make_context(*args, **kwargs)

        return fallback


class _FakeRiskEngine:
    """Return an approved decision while recording risk evaluations."""

    def __init__(self) -> None:
        self.contexts: list[Any] = []
        self.decision = SimpleNamespace(
            approved=True,
            status="APPROVED",
            decision_id=str(uuid4()),
            reason="Test risk approval",
        )

    def evaluate(self, context: Any) -> SimpleNamespace:
        self.contexts.append(context)
        return self.decision


class _FakeExecutionEngine:
    """Record whichever approved-decision method the pipeline invokes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("execute", args, kwargs))

    async def execute_decision(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("execute_decision", args, kwargs))

    async def execute_risk_decision(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("execute_risk_decision", args, kwargs))

    async def submit_order(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("submit_order", args, kwargs))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        async def fallback(*args: Any, **kwargs: Any) -> None:
            self.calls.append((name, args, kwargs))

        return fallback


def _tick(timestamp: int, bid: float) -> MarketTickEvent:
    tick = MarketTick(
        symbol="XAUUSD",
        timestamp=timestamp,
        bid=bid,
        ask=bid + 0.10,
        last=bid,
        volume=1,
        volume_real=0.0,
    )
    return MarketTickEvent(
        event_id=uuid4(),
        occurred_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
        tick=tick,
    )


@pytest.mark.anyio
async def test_tick_to_candle_to_strategy_signal_to_risk_and_execution() -> None:
    """Verify the event-driven PAPER path through the execution boundary."""
    bus = EventBus()

    dispatcher = StrategyDispatcher(bus=bus)
    publisher = StrategySignalPublisher(bus=bus)
    manager = StrategyManager(
        dispatcher=dispatcher,
        signal_publisher=publisher,
    )
    candle_builder = LiveCandleBuilder(bus=bus)

    risk_context_provider = _FakeRiskContextProvider()
    risk_engine = _FakeRiskEngine()
    execution_engine = _FakeExecutionEngine()
    pipeline = SignalRiskExecutionPipeline(
        bus=bus,
        risk_engine=risk_engine,
        context_provider=risk_context_provider,
        execution_engine=execution_engine,
    )

    completed_candles: list[MarketCandleEvent] = []
    signal_events: list[StrategySignalEvent] = []

    async def capture_candle(event: MarketCandleEvent) -> None:
        completed_candles.append(event)

    async def capture_signal(event: StrategySignalEvent) -> None:
        signal_events.append(event)

    await bus.subscribe(MarketCandleEvent, capture_candle)
    await bus.subscribe(StrategySignalEvent, capture_signal)

    config = StrategyConfig(
        strategy_id=f"test-{uuid4()}",
        strategy_name=_TEST_STRATEGY_NAME,
        mode=StrategyMode.PAPER,
        enabled=True,
        symbols=["XAUUSD"],
        timeframes=["M1"],
        parameters={},
        account_id=uuid4(),
    )

    started_components: list[Any] = []
    try:
        # Subscribers must be active before tick events are emitted.
        await candle_builder.start()
        started_components.append(candle_builder)

        await pipeline.start()
        started_components.append(pipeline)

        await manager.start()
        started_components.append(manager)

        await manager.create(config, auto_start=True)

        # The candle builder intentionally discards the first partial bucket
        # after startup. Three consecutive M1 buckets cause the second one
        # to be emitted as a completed candle.
        start = 1_700_000_040
        await bus.publish(_tick(start, 2_000.0))
        await bus.publish(_tick(start + 60, 2_001.0))
        await bus.publish(_tick(start + 120, 2_002.0))

        completed_m1 = [
            event
            for event in completed_candles
            if event.symbol == "XAUUSD" and event.timeframe == "M1"
        ]
        assert completed_m1, "LiveCandleBuilder did not publish a completed M1 candle."
        assert completed_m1[-1].candle.close == pytest.approx(2_001.0)

        assert signal_events, "The active strategy did not publish a TradingSignal event."
        emitted_signal = signal_events[-1].signal
        assert emitted_signal.strategy_id == config.strategy_id
        assert emitted_signal.symbol == "XAUUSD"
        assert emitted_signal.timeframe == "M1"

        assert len(risk_engine.contexts) == 1, "Signal did not reach risk evaluation."
        assert execution_engine.calls, "Approved risk decision did not reach execution."
    finally:
        # Stop consumers before the candle builder to prevent new events while
        # other event subscribers are being removed.
        for component in reversed(started_components):
            await component.stop()

        await bus.unsubscribe(MarketCandleEvent, capture_candle)
        await bus.unsubscribe(StrategySignalEvent, capture_signal)
