"""Trading-signal publishing for the AQE Strategy Runtime."""

from __future__ import annotations

import logging
from typing import Protocol

from app.events import EventBus, event_bus
from app.events.strategy import StrategySignalEvent

from ..core import TradingSignal

logger = logging.getLogger(__name__)


class SignalPublisher(Protocol):
    """
    Protocol for publishing strategy-generated trading signals.

    Strategy implementations depend on this interface rather than
    directly depending on the AQE EventBus.
    """

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """Publish a trading signal and return its event."""


class StrategySignalPublisher:
    """
    Publish strategy signals through the existing AQE EventBus.

    This component is intentionally small. Its only responsibility is
    converting a TradingSignal into a StrategySignalEvent and publishing
    that event.

    It does not:
        - perform risk checks
        - calculate position size
        - create broker orders
        - communicate with MT5
        - communicate with Redis
        - persist signals directly to PostgreSQL
    """

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
    ) -> None:
        """Initialize the signal publisher."""

        self._event_bus = bus or event_bus

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Publish a TradingSignal as a StrategySignalEvent.

        Args:
            signal:
                Validated trading intent produced by a strategy.

        Returns:
            The event that was published.
        """

        event = StrategySignalEvent.create(
            signal=signal,
        )

        await self._event_bus.publish(event)

        logger.info(
            "Strategy signal published: "
            "signal_id=%s strategy_id=%s strategy=%s "
            "symbol=%s timeframe=%s direction=%s type=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.strategy_name,
            signal.symbol,
            signal.timeframe.value,
            signal.direction.value,
            signal.signal_type.value,
        )

        return event


strategy_signal_publisher = StrategySignalPublisher()
