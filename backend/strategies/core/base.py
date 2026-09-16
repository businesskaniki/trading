
"""Base strategy contract for the AQE Strategy Engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.events.market import MarketCandleEvent, MarketTickEvent

from .context import StrategyContext
from .enums import StrategyMode, StrategyStatus
from .exceptions import (
    StrategyConfigurationError,
    StrategyExecutionError,
    StrategyInitializationError,
    StrategyStateError,
)
from .signal import TradingSignal


StrategySignalResult = TradingSignal | Sequence[TradingSignal] | None


class StrategyDefinition(BaseModel):
    """Static metadata describing a strategy implementation."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="1.0.0", min_length=1, max_length=32)
    description: str = ""
    author: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("name", "version", "description", "author")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        """Normalize string metadata."""
        return value.strip()


class StrategyConfig(BaseModel):
    """
    Runtime configuration for a strategy instance.

    One strategy implementation can have many independent instances,
    each with its own symbols, timeframes, parameters, and execution mode.
    """

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
    )

    strategy_id: str = Field(min_length=1, max_length=128)
    strategy_name: str = Field(min_length=1, max_length=128)
    mode: StrategyMode = StrategyMode.PAPER
    enabled: bool = True

    symbols: list[str] = Field(min_length=1)
    timeframes: list[str] = Field(min_length=1)

    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_id", "strategy_name")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        """Normalize strategy identifiers."""
        value = value.strip()

        if not value:
            raise StrategyConfigurationError(
                "Strategy identifiers cannot be empty."
            )

        return value

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(
        cls,
        values: list[str],
    ) -> list[str]:
        """Normalize configured symbols and remove duplicates."""

        normalized: list[str] = []

        for symbol in values:
            symbol = symbol.strip()

            if not symbol:
                continue

            if symbol not in normalized:
                normalized.append(symbol)

        if not normalized:
            raise StrategyConfigurationError(
                "A strategy must contain at least one symbol."
            )

        return normalized

    @field_validator("timeframes")
    @classmethod
    def normalize_timeframes(
        cls,
        values: list[str],
    ) -> list[str]:
        """Normalize configured timeframes and remove duplicates."""

        normalized: list[str] = []

        for timeframe in values:
            timeframe = timeframe.strip().upper()

            if not timeframe:
                continue

            if timeframe not in normalized:
                normalized.append(timeframe)

        if not normalized:
            raise StrategyConfigurationError(
                "A strategy must contain at least one timeframe."
            )

        return normalized


class BaseStrategy(ABC):
    """
    Abstract base class for all AQE trading strategies.

    Strategy implementations receive normalized AQE market-data events
    and return TradingSignal objects representing trading intent.

    Strategies do not:
        - publish EventBus events
        - consume Redis
        - communicate with MT5
        - communicate with brokers
        - perform order execution
        - calculate final position sizing
    """

    definition: StrategyDefinition

    def __init__(
        self,
        config: StrategyConfig,
        context: StrategyContext,
    ) -> None:
        """Create a strategy instance."""

        if config.strategy_id != context.strategy_id:
            raise StrategyConfigurationError(
                "Strategy configuration and context IDs do not match."
            )

        if config.strategy_name != context.strategy_name:
            raise StrategyConfigurationError(
                "Strategy configuration and context names do not match."
            )

        if config.mode != context.mode:
            raise StrategyConfigurationError(
                "Strategy configuration and context modes do not match."
            )

        self.config = config
        self.context = context
        self.status = StrategyStatus.CREATED

    @property
    def strategy_id(self) -> str:
        """Return unique strategy instance identifier."""

        return self.config.strategy_id

    @property
    def strategy_name(self) -> str:
        """Return registered strategy name."""

        return self.config.strategy_name

    @property
    def mode(self) -> StrategyMode:
        """Return execution mode."""

        return self.config.mode

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return symbols monitored by this strategy instance."""

        return self.context.symbols

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Return candle timeframes monitored by this strategy instance."""

        return self.context.timeframes

    @property
    def is_running(self) -> bool:
        """Return whether strategy is currently running."""

        return self.status is StrategyStatus.RUNNING

    @property
    def is_active(self) -> bool:
        """Return whether strategy can process market data."""

        return self.status in {
            StrategyStatus.READY,
            StrategyStatus.RUNNING,
        }

    def supports_symbol(
        self,
        symbol: str,
    ) -> bool:
        """Return whether strategy monitors a symbol."""

        return self.context.supports_symbol(symbol)

    def supports_timeframe(
        self,
        timeframe: str,
    ) -> bool:
        """Return whether strategy monitors a timeframe."""

        return self.context.supports_timeframe(timeframe)

    def supports_tick(
        self,
        symbol: str,
    ) -> bool:
        """
        Return whether strategy should receive a tick event.

        Tick processing is enabled when TICK is included in the
        configured timeframes.
        """

        return (
            self.supports_symbol(symbol)
            and "TICK" in self.timeframes
        )

    def supports_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Return whether strategy should receive a candle event."""

        return (
            self.supports_symbol(symbol)
            and self.supports_timeframe(timeframe)
        )

    async def initialize(self) -> None:
        """Initialize strategy before it can start."""

        if self.status is not StrategyStatus.CREATED:
            raise StrategyStateError(
                f"Cannot initialize strategy '{self.strategy_id}' "
                f"from state '{self.status}'."
            )

        self.status = StrategyStatus.INITIALIZING

        try:
            await self.on_initialize()

        except Exception as exc:
            self.status = StrategyStatus.ERROR

            raise StrategyInitializationError(
                f"Failed to initialize strategy '{self.strategy_id}'."
            ) from exc

        self.status = StrategyStatus.READY

    async def start(self) -> None:
        """Start processing market data."""

        if self.status is StrategyStatus.CREATED:
            await self.initialize()

        if self.status not in {
            StrategyStatus.READY,
            StrategyStatus.PAUSED,
        }:
            raise StrategyStateError(
                f"Cannot start strategy '{self.strategy_id}' "
                f"from state '{self.status}'."
            )

        try:
            if self.status is StrategyStatus.PAUSED:
                await self.on_resume()
            else:
                await self.on_start()

        except Exception as exc:
            self.status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Failed to start strategy '{self.strategy_id}'."
            ) from exc

        self.status = StrategyStatus.RUNNING

    async def pause(self) -> None:
        """Pause market-data processing."""

        if self.status is not StrategyStatus.RUNNING:
            raise StrategyStateError(
                f"Cannot pause strategy '{self.strategy_id}' "
                f"from state '{self.status}'."
            )

        try:
            await self.on_pause()

        except Exception as exc:
            self.status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Failed to pause strategy '{self.strategy_id}'."
            ) from exc

        self.status = StrategyStatus.PAUSED

    async def resume(self) -> None:
        """Resume a paused strategy."""

        if self.status is not StrategyStatus.PAUSED:
            raise StrategyStateError(
                f"Cannot resume strategy '{self.strategy_id}' "
                f"from state '{self.status}'."
            )

        try:
            await self.on_resume()

        except Exception as exc:
            self.status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Failed to resume strategy '{self.strategy_id}'."
            ) from exc

        self.status = StrategyStatus.RUNNING

    async def stop(self) -> None:
        """Stop strategy."""

        if self.status in {
            StrategyStatus.STOPPED,
            StrategyStatus.CREATED,
        }:
            self.status = StrategyStatus.STOPPED
            return

        self.status = StrategyStatus.STOPPING

        try:
            await self.on_stop()

        except Exception as exc:
            self.status = StrategyStatus.ERROR

            raise StrategyExecutionError(
                f"Failed to stop strategy '{self.strategy_id}'."
            ) from exc

        self.status = StrategyStatus.STOPPED

    async def handle_tick(
        self,
        event: MarketTickEvent,
    ) -> StrategySignalResult:
        """
        Process a normalized AQE market-tick event.

        Returns:
            A TradingSignal, multiple TradingSignals, or None.
        """

        if not self.is_active:
            return None

        if not self.supports_tick(event.symbol):
            return None

        try:
            result = await self.on_tick(event)
            return self._validate_signal_result(result)

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed while "
                f"processing tick for '{event.symbol}'."
            ) from exc

    async def handle_candle(
        self,
        event: MarketCandleEvent,
    ) -> StrategySignalResult:
        """
        Process a normalized AQE market-candle event.

        Returns:
            A TradingSignal, multiple TradingSignals, or None.
        """

        if not self.is_active:
            return None

        if not self.supports_candle(
            event.symbol,
            event.timeframe,
        ):
            return None

        try:
            result = await self.on_candle(event)
            return self._validate_signal_result(result)

        except StrategyExecutionError:
            raise

        except Exception as exc:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' failed while "
                f"processing {event.timeframe} candle for "
                f"'{event.symbol}'."
            ) from exc

    def _validate_signal_result(
        self,
        result: StrategySignalResult,
    ) -> StrategySignalResult:
        """
        Validate the result returned by a strategy hook.

        This performs structural validation only. TradingSignal itself
        remains responsible for validating its own fields and price
        relationships.
        """

        if result is None:
            return None

        if isinstance(result, TradingSignal):
            self._validate_signal(result)
            return result

        if isinstance(result, Sequence) and not isinstance(
            result,
            (str, bytes, bytearray),
        ):
            signals = list(result)

            for signal in signals:
                self._validate_signal(signal)

            return signals

        raise StrategyExecutionError(
            f"Strategy '{self.strategy_id}' returned an invalid "
            f"signal result of type '{type(result).__name__}'."
        )

    def _validate_signal(
        self,
        signal: TradingSignal,
    ) -> None:
        """Validate that a signal belongs to this strategy instance."""

        if signal.strategy_id != self.strategy_id:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' returned a signal "
                f"belonging to strategy '{signal.strategy_id}'."
            )

        if signal.strategy_name != self.strategy_name:
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' returned a signal "
                f"with strategy name '{signal.strategy_name}'."
            )

        if not self.supports_symbol(signal.symbol):
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' returned a signal "
                f"for unsupported symbol '{signal.symbol}'."
            )

        if not self.supports_timeframe(
            signal.timeframe.value,
        ):
            raise StrategyExecutionError(
                f"Strategy '{self.strategy_id}' returned a signal "
                f"for unsupported timeframe "
                f"'{signal.timeframe.value}'."
            )

    async def on_initialize(self) -> None:
        """Hook called during strategy initialization."""

    async def on_start(self) -> None:
        """Hook called when strategy starts."""

    async def on_pause(self) -> None:
        """Hook called when strategy pauses."""

    async def on_resume(self) -> None:
        """Hook called when strategy resumes."""

    async def on_stop(self) -> None:
        """Hook called when strategy stops."""

    async def on_tick(
        self,
        event: MarketTickEvent,
    ) -> TradingSignal | Sequence[TradingSignal] | None:
        """Handle a market tick.

        Subclasses may override this hook to implement tick-based logic.
        """
        return None

    @abstractmethod
    async def on_candle(
        self,
        event: MarketCandleEvent,
    ) -> TradingSignal | Sequence[TradingSignal] | None:
        """Handle a market candle."""