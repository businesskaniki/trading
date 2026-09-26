"""Signal delivery services for the AQE Strategy Engine."""

from __future__ import annotations

import logging
from typing import Protocol

from app.events import event_bus
from app.events.strategy import StrategySignalEvent

from ..core.signal import TradingSignal

logger = logging.getLogger(__name__)


class SignalPublisher(Protocol):
    """
    Convert a TradingSignal into a StrategySignalEvent.

    Implementations decide whether the resulting event is delivered
    to the global runtime event bus or returned directly to the caller.
    """

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """Create and deliver a strategy signal event."""
        ...


class StrategySignalPublisher:
    """
    Publish strategy signals to the AQE EventBus.

    This is the live/paper runtime publisher. It is intentionally
    independent from strategy implementation code.
    """

    def __init__(self, *, bus=None) -> None:
        self._event_bus = bus or event_bus

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Convert a TradingSignal into a StrategySignalEvent and publish it.
        """

        event = StrategySignalEvent.create(
            signal=signal,
        )

        await self._event_bus.publish(
            event,
        )

        logger.info(
            "Strategy signal published: "
            "signal_id=%s strategy_id=%s symbol=%s direction=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.symbol,
            signal.direction.value,
        )

        return event


class BacktestSignalPublisher:
    """
    Convert strategy signals into StrategySignalEvents without publishing
    them to the global EventBus.

    Backtests consume the returned events directly through the
    BacktestOrchestrator. This prevents simulated strategy signals from
    entering the live SignalRiskExecutionPipeline.
    """

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Create a StrategySignalEvent without external delivery.
        """

        event = StrategySignalEvent.create(
            signal=signal,
        )

        logger.debug(
            "Backtest strategy signal created: "
            "signal_id=%s strategy_id=%s symbol=%s direction=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.symbol,
            signal.direction.value,
        )

        return event


strategy_signal_publisher = StrategySignalPublisher()
