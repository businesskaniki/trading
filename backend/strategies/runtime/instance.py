"""Runtime wrapper for individual AQE strategy instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.events.market import MarketCandleEvent, MarketTickEvent
from app.events.strategy import StrategySignalEvent

from ..core import (
    BaseStrategy,
    StrategyConfig,
    StrategyContext,
    StrategyDefinition,
    StrategyMode,
    StrategyStatus,
    TradingSignal,
    registry,
)
from ..core.exceptions import StrategyExecutionError
from .signal_publisher import StrategySignalPublisher


@dataclass(slots=True)
class StrategyInstance:
    """
    Runtime representation of one configured strategy instance.

    A registered strategy class can have multiple independent
    StrategyInstance objects, each with its own configuration,
    context, lifecycle, and state.

    The instance is also the boundary between strategy logic and
    runtime infrastructure. Strategies return TradingSignal objects;
    the instance passes those signals to the configured publisher.
    """

    strategy: BaseStrategy
    signal_publisher: StrategySignalPublisher

    @property
    def strategy_id(self) -> str:
        """Return the unique instance identifier."""
        return self.strategy.strategy_id

    @property
    def strategy_name(self) -> str:
        """Return the registered strategy name."""
        return self.strategy.strategy_name

    @property
    def mode(self) -> StrategyMode:
        """Return the execution mode."""
        return self.strategy.mode

    @property
    def status(self) -> StrategyStatus:
        """Return current lifecycle state."""
        return self.strategy.status

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return symbols monitored by this instance."""
        return self.strategy.symbols

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Return timeframes monitored by this instance."""
        return self.strategy.timeframes

    @property
    def definition(self) -> StrategyDefinition:
        """Return strategy implementation definition."""
        return self.strategy.definition

    @property
    def config(self) -> StrategyConfig:
        """Return instance configuration."""
        return self.strategy.config

    @property
    def context(self) -> StrategyContext:
        """Return runtime strategy context."""
        return self.strategy.context

    @property
    def is_running(self) -> bool:
        """Return whether strategy is running."""
        return self.strategy.is_running

    @property
    def is_active(self) -> bool:
        """Return whether strategy can process market data."""
        return self.strategy.is_active

    @classmethod
    def create(
        cls,
        config: StrategyConfig,
        *,
        market_data: Any | None = None,
        positions: Any | None = None,
        state: Any | None = None,
        clock: Any | None = None,
        signal_publisher: StrategySignalPublisher | None = None,
    ) -> StrategyInstance:
        """
        Create a strategy instance from runtime configuration.

        The concrete strategy implementation is resolved through the
        global strategy registry.
        """

        strategy_class = registry.get(
            config.strategy_name,
        )

        context_kwargs: dict[str, Any] = {
            "strategy_id": config.strategy_id,
            "strategy_name": config.strategy_name,
            "mode": config.mode,
            "symbols": tuple(config.symbols),
            "timeframes": tuple(config.timeframes),
            "parameters": dict(config.parameters),
            "metadata": dict(config.metadata),
        }

        if market_data is not None:
            context_kwargs["market_data"] = market_data

        if positions is not None:
            context_kwargs["positions"] = positions

        if state is not None:
            context_kwargs["state"] = state

        if clock is not None:
            context_kwargs["clock"] = clock

        context = StrategyContext(
            **context_kwargs,
        )

        strategy = strategy_class(
            config=config,
            context=context,
        )

        return cls(
            strategy=strategy,
            signal_publisher=(signal_publisher or StrategySignalPublisher()),
        )

    async def initialize(self) -> None:
        """Initialize the underlying strategy."""
        await self.strategy.initialize()

    async def start(self) -> None:
        """Start the underlying strategy."""
        await self.strategy.start()

    async def pause(self) -> None:
        """Pause the underlying strategy."""
        await self.strategy.pause()

    async def resume(self) -> None:
        """Resume the underlying strategy."""
        await self.strategy.resume()

    async def stop(self) -> None:
        """Stop the underlying strategy."""
        await self.strategy.stop()

    def supports_tick(
        self,
        symbol: str,
    ) -> bool:
        """Return whether this instance should receive a tick."""
        return self.strategy.supports_tick(symbol)

    def supports_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Return whether this instance should receive a candle."""
        return self.strategy.supports_candle(
            symbol=symbol,
            timeframe=timeframe,
        )

    async def handle_tick(
        self,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a tick and publish any generated signals.

        Returns:
            Published strategy-signal events.
        """

        try:
            result = await self.strategy.handle_tick(
                event,
            )

            return await self._publish_signals(
                result,
            )

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' "
                f"failed while handling a tick."
            ) from exc

    async def handle_candle(
        self,
        event: MarketCandleEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a candle and publish any generated signals.

        Returns:
            Published strategy-signal events.
        """

        try:
            result = await self.strategy.handle_candle(
                event,
            )

            return await self._publish_signals(
                result,
            )

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' "
                f"failed while handling a candle."
            ) from exc

    async def _publish_signals(
        self,
        result: TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Publish strategy-generated signals.

        A strategy may return:
            None
            one TradingSignal
            a list/tuple of TradingSignal objects

        The publisher converts each signal into a
        StrategySignalEvent and sends it through the existing AQE
        EventBus.
        """

        if result is None:
            return ()

        if isinstance(result, TradingSignal):
            signals = (result,)
        else:
            signals = tuple(result)

        if not signals:
            return ()

        published_events: list[StrategySignalEvent] = []

        for signal in signals:
            event = await self.signal_publisher.publish(
                signal,
            )

            published_events.append(event)

        return tuple(published_events)

    def snapshot(self) -> dict[str, Any]:
        """
        Return a lightweight runtime snapshot.

        Intended for monitoring, diagnostics, and management APIs.
        Does not expose sensitive runtime objects.
        """

        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "mode": self.mode.value,
            "status": self.status.value,
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "enabled": self.config.enabled,
        }

    def __repr__(self) -> str:
        """Return useful representation for logs/debugging."""

        return (
            "StrategyInstance("
            f"strategy_id={self.strategy_id!r}, "
            f"strategy_name={self.strategy_name!r}, "
            f"mode={self.mode.value!r}, "
            f"status={self.status.value!r}"
            ")"
        )
