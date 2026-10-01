"""Signal delivery services for the AQE Strategy Engine."""

from __future__ import annotations

import logging
from typing import Protocol

from app.events import EventBus, event_bus
from app.events.strategy import StrategySignalEvent

from ..core.signal import TradingSignal

logger = logging.getLogger(__name__)


class SignalPublisher(Protocol):
    """
    Protocol for strategy signal delivery.

    A publisher receives a strategy-generated TradingSignal and converts
    it into a StrategySignalEvent.

    The publisher does not:

        - perform risk checks
        - calculate position size
        - create execution orders
        - communicate with brokers
        - place orders

    Those responsibilities belong to downstream AQE components.
    """

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Convert and deliver a TradingSignal.

        Returns:
            The resulting StrategySignalEvent.
        """
        ...


class StrategySignalPublisher:
    """
    Publish LIVE/PAPER strategy signals to the AQE EventBus.

    This class forms the boundary between:

        Strategy Engine
              │
              ▼
        TradingSignal
              │
              ▼
        StrategySignalEvent
              │
              ▼
          EventBus
              │
              ▼
          Risk Engine

    The publisher does not perform any trading decision after receiving
    the TradingSignal.
    """

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
    ) -> None:
        """Initialize the signal publisher."""

        self._event_bus = bus if bus is not None else event_bus

    @property
    def event_bus(self) -> EventBus:
        """Return the EventBus used for signal delivery."""

        return self._event_bus

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Convert a TradingSignal into a StrategySignalEvent and publish it.

        The resulting event is delivered to the shared AQE EventBus.

        Downstream consumers such as the Risk Engine are responsible for
        deciding what happens to the signal.
        """

        self._validate_signal(
            signal,
        )

        event = StrategySignalEvent.create(
            signal=signal,
        )

        await self._event_bus.publish(
            event,
        )

        logger.info(
            "Strategy signal published: "
            "signal_id=%s strategy_id=%s "
            "symbol=%s direction=%s signal_type=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.symbol,
            signal.direction.value,
            signal.signal_type.value,
        )

        return event

    @staticmethod
    def _validate_signal(
        signal: TradingSignal,
    ) -> None:
        """Validate the publisher input."""

        if not isinstance(
            signal,
            TradingSignal,
        ):
            raise TypeError(
                "StrategySignalPublisher expects a " "TradingSignal instance."
            )


class BacktestSignalPublisher:
    """
    Create StrategySignalEvents without publishing them to EventBus.

    Backtests consume the returned events directly.

    This isolation is intentional:

        BACKTEST
            Strategy
               │
               ▼
         TradingSignal
               │
               ▼
      StrategySignalEvent
               │
               ▼
        BacktestOrchestrator
               │
               ▼
          Risk Engine
               │
               ▼
       Backtest Execution

    A simulated backtest signal must never accidentally enter the
    LIVE/PAPER EventBus and reach the live trading pipeline.
    """

    async def publish(
        self,
        signal: TradingSignal,
    ) -> StrategySignalEvent:
        """
        Create a StrategySignalEvent without external delivery.

        Returns:
            The event for direct consumption by the backtest runtime.
        """

        self._validate_signal(
            signal,
        )

        event = StrategySignalEvent.create(
            signal=signal,
        )

        logger.debug(
            "Backtest strategy signal created: "
            "signal_id=%s strategy_id=%s "
            "symbol=%s direction=%s signal_type=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.symbol,
            signal.direction.value,
            signal.signal_type.value,
        )

        return event

    @staticmethod
    def _validate_signal(
        signal: TradingSignal,
    ) -> None:
        """Validate the publisher input."""

        if not isinstance(
            signal,
            TradingSignal,
        ):
            raise TypeError(
                "BacktestSignalPublisher expects a " "TradingSignal instance."
            )


strategy_signal_publisher = StrategySignalPublisher()
