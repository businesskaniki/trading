"""Runtime context and supporting protocols for AQE strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .enums import StrategyMode


class MarketDataView(Protocol):
    """
    Read-only interface for strategy market-data access.

    Implementations belong outside the Strategy Core. This keeps
    strategies independent from MT5, Redis, HTTP, and database
    infrastructure.
    """

    async def get_latest_tick(self, symbol: str) -> Any | None:
        """Return the latest known tick for a symbol."""

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list[Any]:
        """Return recent candles for a symbol and timeframe."""

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Any]:
        """Return historical candles for a symbol and timeframe."""


class PositionView(Protocol):
    """
    Read-only interface for strategy position information.

    Position sizing and risk decisions remain the responsibility of
    the Risk Engine.
    """

    async def get_position(
        self,
        symbol: str,
    ) -> Any | None:
        """Return the current position for a symbol."""

    async def get_positions(
        self,
        symbols: list[str] | None = None,
    ) -> list[Any]:
        """Return current positions, optionally filtered by symbols."""


class StrategyStateStore(Protocol):
    """
    Persistent or runtime state interface for strategies.

    The concrete implementation is supplied by the runtime layer.
    """

    async def get(
        self,
        strategy_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Retrieve a strategy state value."""

    async def set(
        self,
        strategy_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Store a strategy state value."""

    async def delete(
        self,
        strategy_id: str,
        key: str,
    ) -> None:
        """Delete a strategy state value."""


class Clock(Protocol):
    """Clock abstraction used to make strategies testable."""

    def now(self) -> datetime:
        """Return the current UTC time."""


class SystemClock:
    """Default production clock using the system UTC time."""

    def now(self) -> datetime:
        """Return the current UTC time."""

        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Minimal position information exposed to a strategy."""

    symbol: str
    side: str
    quantity: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyContext:
    """
    Runtime context supplied to a strategy instance.

    The context contains strategy-specific configuration and access
    to read-only runtime services. It does not own broker connections,
    market-data subscriptions, Redis consumers, or order execution.
    """

    strategy_id: str
    strategy_name: str
    mode: StrategyMode

    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]

    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    market_data: MarketDataView | None = None
    positions: PositionView | None = None
    state: StrategyStateStore | None = None

    clock: Clock = field(default_factory=SystemClock)

    def __post_init__(self) -> None:
        """Normalize context identifiers and configuration."""

        self.strategy_id = self.strategy_id.strip()
        self.strategy_name = self.strategy_name.strip()

        self.symbols = tuple(
            symbol.strip() for symbol in self.symbols if symbol and symbol.strip()
        )

        self.timeframes = tuple(
            timeframe.strip().upper()
            for timeframe in self.timeframes
            if timeframe and timeframe.strip()
        )

        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty.")

        if not self.strategy_name:
            raise ValueError("strategy_name cannot be empty.")

        if not self.symbols:
            raise ValueError("A strategy context must contain at least one symbol.")

        if not self.timeframes:
            raise ValueError("A strategy context must contain at least one timeframe.")

    def supports_symbol(self, symbol: str) -> bool:
        """Return True when the strategy monitors the given symbol."""

        return symbol.strip() in self.symbols

    def supports_timeframe(self, timeframe: str) -> bool:
        """Return True when the strategy monitors the given timeframe."""

        return timeframe.strip().upper() in self.timeframes

    def supports(
        self,
        symbol: str,
        timeframe: str | None = None,
    ) -> bool:
        """
        Return whether this strategy should process the data.

        For tick data, timeframe can be omitted because ticks do not
        have a candle timeframe.
        """

        if not self.supports_symbol(symbol):
            return False

        if timeframe is None:
            return True

        return self.supports_timeframe(timeframe)

    def parameter(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """Return a configured strategy parameter."""

        return self.parameters.get(name, default)

    def now(self) -> datetime:
        """Return the current strategy clock time."""

        return self.clock.now()

    async def get_latest_tick(
        self,
        symbol: str,
    ) -> Any | None:
        """Read the latest tick through the configured market-data view."""

        if self.market_data is None:
            return None

        return await self.market_data.get_latest_tick(symbol)

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list[Any]:
        """Read recent candles through the configured market-data view."""

        if self.market_data is None:
            return []

        return await self.market_data.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Any]:
        """Read historical candles through the configured market-data view."""

        if self.market_data is None:
            return []

        return await self.market_data.get_historical_candles(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

    async def get_position(
        self,
        symbol: str,
    ) -> Any | None:
        """Read the current position for a symbol."""

        if self.positions is None:
            return None

        return await self.positions.get_position(symbol)

    async def get_positions(
        self,
        symbols: list[str] | None = None,
    ) -> list[Any]:
        """Read current positions."""

        if self.positions is None:
            return []

        return await self.positions.get_positions(symbols)

    async def get_state(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Read strategy-specific state."""

        if self.state is None:
            return default

        return await self.state.get(
            strategy_id=self.strategy_id,
            key=key,
            default=default,
        )

    async def set_state(
        self,
        key: str,
        value: Any,
    ) -> None:
        """Persist strategy-specific state."""

        if self.state is None:
            return

        await self.state.set(
            strategy_id=self.strategy_id,
            key=key,
            value=value,
        )

    async def delete_state(
        self,
        key: str,
    ) -> None:
        """Delete strategy-specific state."""

        if self.state is None:
            return

        await self.state.delete(
            strategy_id=self.strategy_id,
            key=key,
        )
