"""End-to-end tests for the AQE Strategy Runtime."""

from __future__ import annotations

import pytest

from app.events.bus import EventBus
from app.events.market import MarketCandleEvent
from app.events.strategy import StrategySignalEvent
from app.market_data.models import MarketCandle

from strategies.core import (
    StrategyConfig,
    StrategyMode,
    Timeframe,
)
from strategies.runtime import (
    StrategyManager,
    StrategySignalPublisher,
)


@pytest.fixture
def anyio_backend() -> str:
    """Run AnyIO tests exclusively on the asyncio backend."""
    return "asyncio"


@pytest.fixture
def strategy_config() -> StrategyConfig:
    """Return a strategy configuration for integration tests."""
    return StrategyConfig(
        strategy_id="integration-test-001",
        strategy_name="integration_test",
        mode=StrategyMode.PAPER,
        enabled=True,
        symbols=["EURUSD"],
        timeframes=["M15"],
        parameters={
            "stop_loss_percent": 0.01,
            "take_profit_percent": 0.02,
            "confidence": 1.0,
        },
    )


@pytest.fixture
def candle() -> MarketCandle:
    """Return a bullish EURUSD M15 candle."""
    return MarketCandle(
        symbol="EURUSD",
        timeframe="M15",
        timestamp=1_757_500_000,
        open=1.10000,
        high=1.10250,
        low=1.09900,
        close=1.10100,
        volume=100,
        spread=10,
    )


@pytest.mark.anyio
async def test_market_candle_generates_strategy_signal(
    strategy_config: StrategyConfig,
    candle: MarketCandle,
) -> None:
    """A bullish candle should generate a long strategy signal."""

    event_bus = EventBus()
    signal_publisher = StrategySignalPublisher(
        bus=event_bus,
    )
    manager = StrategyManager(
        signal_publisher=signal_publisher,
    )

    received_events: list[StrategySignalEvent] = []

    async def handle_signal(
        event: StrategySignalEvent,
    ) -> None:
        received_events.append(event)

    await event_bus.subscribe(
        StrategySignalEvent,
        handle_signal,
    )

    try:
        await manager.start()

        instance = await manager.create(
            strategy_config,
            auto_start=True,
        )

        assert instance.strategy_id == "integration-test-001"
        assert instance.strategy_name == "integration_test"
        assert instance.status.value == "running"

        market_event = MarketCandleEvent.create(
            candle=candle,
        )

        signal_events = await manager.dispatcher.dispatch_candle(
            market_event,
        )

        assert len(signal_events) == 1
        assert len(received_events) == 1

        signal_event = signal_events[0]

        assert isinstance(
            signal_event,
            StrategySignalEvent,
        )

        signal = signal_event.signal

        assert signal.strategy_id == "integration-test-001"
        assert signal.strategy_name == "integration_test"
        assert signal.symbol == "EURUSD"
        assert signal.timeframe is Timeframe.M15
        assert signal.direction.value == "long"
        assert signal.signal_type.value == "entry"
        assert signal.order_type.value == "market"

        assert signal.entry_price == candle.close

        assert signal.stop_loss < signal.entry_price
        assert signal.entry_price < signal.take_profit

        assert signal.confidence == 1.0

        assert received_events[0].signal.signal_id == signal.signal_id

    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_bearish_candle_generates_short_signal(
    strategy_config: StrategyConfig,
) -> None:
    """A bearish candle should generate a short strategy signal."""

    manager = StrategyManager()

    try:
        await manager.start()

        instance = await manager.create(
            strategy_config,
            auto_start=True,
        )

        bearish_candle = MarketCandle(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=1_757_500_000,
            open=1.10100,
            high=1.10200,
            low=1.09800,
            close=1.09900,
            volume=100,
            spread=10,
        )

        market_event = MarketCandleEvent.create(
            candle=bearish_candle,
        )

        signal_events = await manager.dispatcher.dispatch_candle(
            market_event,
        )

        assert len(signal_events) == 1

        signal = signal_events[0].signal

        assert signal.direction.value == "short"

        assert signal.stop_loss > signal.entry_price
        assert signal.take_profit < signal.entry_price

        assert signal.entry_price == bearish_candle.close
        assert instance.status.value == "running"

    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_doji_does_not_generate_signal(
    strategy_config: StrategyConfig,
) -> None:
    """A doji candle should not generate a strategy signal."""

    manager = StrategyManager()

    try:
        await manager.start()

        await manager.create(
            strategy_config,
            auto_start=True,
        )

        doji = MarketCandle(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=1_757_500_000,
            open=1.10000,
            high=1.10100,
            low=1.09900,
            close=1.10000,
            volume=100,
            spread=10,
        )

        market_event = MarketCandleEvent.create(
            candle=doji,
        )

        signal_events = await manager.dispatcher.dispatch_candle(
            market_event,
        )

        assert signal_events == ()

    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_strategy_ignores_unsupported_symbol(
    strategy_config: StrategyConfig,
    candle: MarketCandle,
) -> None:
    """A strategy should ignore symbols outside its configured universe."""

    manager = StrategyManager()

    try:
        await manager.start()

        await manager.create(
            strategy_config,
            auto_start=True,
        )

        gbpusd_candle = MarketCandle(
            symbol="GBPUSD",
            timeframe="M15",
            timestamp=candle.timestamp,
            open=1.25000,
            high=1.25200,
            low=1.24900,
            close=1.25100,
            volume=100,
            spread=10,
        )

        market_event = MarketCandleEvent.create(
            candle=gbpusd_candle,
        )

        signal_events = await manager.dispatcher.dispatch_candle(
            market_event,
        )

        assert signal_events == ()

    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_strategy_ignores_unsupported_timeframe(
    strategy_config: StrategyConfig,
) -> None:
    """A strategy should ignore timeframes outside its configuration."""

    manager = StrategyManager()

    try:
        await manager.start()

        await manager.create(
            strategy_config,
            auto_start=True,
        )

        h1_candle = MarketCandle(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=1_757_500_000,
            open=1.10000,
            high=1.10300,
            low=1.09900,
            close=1.10200,
            volume=100,
            spread=10,
        )

        market_event = MarketCandleEvent.create(
            candle=h1_candle,
        )

        signal_events = await manager.dispatcher.dispatch_candle(
            market_event,
        )

        assert signal_events == ()

    finally:
        await manager.stop()
