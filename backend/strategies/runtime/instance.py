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

    A registered strategy implementation can have multiple independent
    StrategyInstance objects.

    Each instance owns:

        - one BaseStrategy object
        - one StrategyConfig
        - one StrategyContext
        - one selected symbol universe
        - one lifecycle
        - one activation state
        - one strategy-specific runtime state

    A strategy instance may analyse multiple symbols.

    Example:

        StrategyInstance
            strategy = EMA Trend
            symbols  = (
                "XAUUSD.s",
                "BTCUSD",
                "AUDCAD.s",
                "EURUSD",
            )

    There is intentionally no one-instance-per-symbol model.

    The instance is also the boundary between strategy logic and
    runtime infrastructure:

        Market Event
              │
              ▼
        StrategyInstance
              │
              ▼
        BaseStrategy
              │
              ▼
        TradingSignal
              │
              ▼
        StrategySignalPublisher
              │
              ▼
        StrategySignalEvent

    The instance is also responsible for enforcing the StrategyRun
    boundary. A strategy implementation may only publish signals that
    belong to this configured strategy instance and its configured
    symbol/timeframe universe.
    """

    strategy: BaseStrategy
    signal_publisher: StrategySignalPublisher

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def strategy_id(self) -> str:
        """Return the unique runtime strategy instance identifier."""

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
        """Return the current lifecycle state."""

        return self.strategy.status

    @property
    def symbols(self) -> tuple[str, ...]:
        """
        Return all symbols monitored by this strategy instance.

        A strategy instance can monitor multiple symbols simultaneously.
        """

        return self.strategy.symbols

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Return all timeframes monitored by this instance."""

        return self.strategy.timeframes

    @property
    def definition(self) -> StrategyDefinition:
        """Return the static strategy implementation definition."""

        return self.strategy.definition

    @property
    def config(self) -> StrategyConfig:
        """Return the runtime strategy configuration."""

        return self.strategy.config

    @property
    def context(self) -> StrategyContext:
        """Return the runtime strategy context."""

        return self.strategy.context

    @property
    def is_enabled(self) -> bool:
        """
        Return whether this strategy instance is administratively
        enabled.
        """

        return self.strategy.is_enabled

    @property
    def is_running(self) -> bool:
        """Return whether the strategy lifecycle is RUNNING."""

        return self.strategy.is_running

    @property
    def is_active(self) -> bool:
        """
        Return whether the strategy is currently allowed to process
        market data.
        """

        return self.strategy.is_active

    # ==================================================================
    # CREATION
    # ==================================================================

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
        Create one runtime strategy instance from configuration.

        The strategy implementation is resolved through the AQE
        StrategyRegistry.

        The registry provides the implementation class only. This method
        then creates exactly one instance configured with the complete
        symbol universe contained in ``config.symbols``.

        No market-data subscription is created here.
        No broker communication occurs here.
        No risk validation occurs here.
        No order execution occurs here.
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
            signal_publisher=(
                signal_publisher
                if signal_publisher is not None
                else StrategySignalPublisher()
            ),
        )

    # ==================================================================
    # ACTIVATION
    # ==================================================================

    def activate(self) -> None:
        """
        Activate this strategy instance.

        Activation is independent of lifecycle state.

        Example:

            RUNNING + activate()
                -> RUNNING + active

        The strategy is not started by this method.
        """

        self.strategy.activate()

    def deactivate(self) -> None:
        """
        Deactivate this strategy instance.

        Deactivation does not stop the lifecycle and does not destroy
        strategy state.

        Example:

            RUNNING + deactivate()
                -> RUNNING + inactive
        """

        self.strategy.deactivate()

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def initialize(self) -> None:
        """Initialize the underlying strategy."""

        await self.strategy.initialize()

    async def start(self) -> None:
        """Start the underlying strategy lifecycle."""

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

    # ==================================================================
    # MARKET-DATA CAPABILITY
    # ==================================================================

    def supports_tick(
        self,
        symbol: str,
    ) -> bool:
        """
        Return whether this strategy instance should receive a tick
        for the supplied symbol.
        """

        return self.strategy.supports_tick(
            symbol,
        )

    def supports_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Return whether this strategy instance should receive a candle
        for the supplied symbol and timeframe.
        """

        return self.strategy.supports_candle(
            symbol=symbol,
            timeframe=timeframe,
        )

    # ==================================================================
    # MARKET-DATA PROCESSING
    # ==================================================================

    async def handle_tick(
        self,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a market tick and publish generated signals.

        The instance performs a defensive capability check before
        invoking the strategy implementation.

        The underlying strategy remains responsible only for analysis.
        Any resulting TradingSignal is validated against this
        StrategyRun before publication.

        Returns:
            Published strategy-signal events.
        """

        try:
            if not self.supports_tick(
                event.symbol,
            ):
                return ()

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
                "failed while handling a tick."
            ) from exc

    async def handle_candle(
        self,
        event: MarketCandleEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a market candle and publish generated signals.

        The instance performs a defensive capability check before
        invoking the strategy implementation.

        Returns:
            Published strategy-signal events.
        """

        try:
            if not self.supports_candle(
                symbol=event.symbol,
                timeframe=event.timeframe,
            ):
                return ()

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
                "failed while handling a candle."
            ) from exc

    # ==================================================================
    # SIGNAL VALIDATION
    # ==================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        """
        Normalize a symbol for runtime comparison.
        """

        return str(symbol).strip().upper()

    @staticmethod
    def _normalize_timeframe(
        timeframe: Any,
    ) -> str:
        """
        Normalize a timeframe for runtime comparison.

        Supports both plain strings and enum-like timeframe values.
        """

        value = getattr(
            timeframe,
            "value",
            timeframe,
        )

        return str(value).strip().upper()

    def _validate_signal(
        self,
        signal: TradingSignal,
    ) -> None:
        """
        Validate a generated signal against this StrategyRun.

        This is the final strategy-runtime boundary before the signal
        enters the downstream AQE signal pipeline.

        A signal is valid only when:

            - it belongs to this strategy instance
            - it belongs to this strategy implementation
            - its symbol is configured for this StrategyRun
            - its timeframe is configured for this StrategyRun
        """

        signal_strategy_id = str(
            signal.strategy_id,
        )

        if signal_strategy_id != str(self.strategy_id):
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' generated "
                f"a signal belonging to strategy instance "
                f"'{signal_strategy_id}'."
            )

        if signal.strategy_name != self.strategy_name:
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' generated "
                f"a signal with strategy_name "
                f"'{signal.strategy_name}', expected "
                f"'{self.strategy_name}'."
            )

        normalized_symbol = self._normalize_symbol(
            signal.symbol,
        )

        allowed_symbols = {self._normalize_symbol(symbol) for symbol in self.symbols}

        if normalized_symbol not in allowed_symbols:
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' "
                f"('{self.strategy_name}') generated a signal for "
                f"symbol '{signal.symbol}', which is outside its "
                f"configured StrategyRun symbol universe "
                f"{self.symbols!r}."
            )

        normalized_timeframe = self._normalize_timeframe(
            signal.timeframe,
        )

        allowed_timeframes = {
            self._normalize_timeframe(timeframe) for timeframe in self.timeframes
        }

        if normalized_timeframe not in allowed_timeframes:
            raise StrategyExecutionError(
                f"Strategy instance '{self.strategy_id}' "
                f"('{self.strategy_name}') generated a signal for "
                f"timeframe '{signal.timeframe}', which is outside "
                f"its configured StrategyRun timeframe universe "
                f"{self.timeframes!r}."
            )

    # ==================================================================
    # SIGNAL PUBLISHING
    # ==================================================================

    async def _publish_signals(
        self,
        result: TradingSignal | list[TradingSignal] | tuple[TradingSignal, ...] | None,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Validate and publish signals generated by the strategy.

        Supported strategy return values:

            None
            TradingSignal
            list[TradingSignal]
            tuple[TradingSignal, ...]

        Every TradingSignal is validated against this StrategyRun
        before it is handed to the signal publisher.

        The StrategyInstance does not perform risk validation,
        position sizing, or execution.

        Those responsibilities belong to downstream AQE components.
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
            if not isinstance(signal, TradingSignal):
                raise StrategyExecutionError(
                    f"Strategy '{self.strategy_id}' returned an "
                    f"unsupported signal type: {type(signal).__name__}."
                )

            self._validate_signal(
                signal,
            )

            event = await self.signal_publisher.publish(
                signal,
            )

            published_events.append(
                event,
            )

        return tuple(published_events)

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(self) -> dict[str, Any]:
        """
        Return a lightweight runtime snapshot.

        Intended for:

            - management APIs
            - frontend state
            - monitoring
            - diagnostics
            - runtime inspection

        Sensitive runtime infrastructure objects are not exposed.
        """

        return self.strategy.snapshot()

    # ==================================================================
    # REPRESENTATION
    # ==================================================================

    def __repr__(self) -> str:
        """Return a useful representation for logs and debugging."""

        return (
            "StrategyInstance("
            f"strategy_id={self.strategy_id!r}, "
            f"strategy_name={self.strategy_name!r}, "
            f"mode={self.mode.value!r}, "
            f"status={self.status.value!r}, "
            f"enabled={self.is_enabled!r}, "
            f"active={self.is_active!r}, "
            f"symbols={self.symbols!r}"
            ")"
        )
