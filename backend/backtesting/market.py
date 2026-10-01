from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Iterable, Iterator, Sequence


class BacktestMarketError(Exception):
    """Base exception for backtest market-data failures."""


class BacktestDataValidationError(BacktestMarketError):
    """Raised when historical market data is invalid."""


class MarketEventType(StrEnum):
    CANDLE = "CANDLE"


@dataclass(frozen=True, slots=True)
class BacktestCandle:
    """
    Immutable OHLC candle used by the backtesting engine.

    The backtesting subsystem owns this lightweight representation
    instead of coupling the engine loop directly to a persistence
    model.
    """

    symbol: str
    timeframe: str
    timestamp: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    volume: Decimal = Decimal("0")
    spread: Decimal | None = None

    def __post_init__(self) -> None:
        symbol = self._normalize_symbol(self.symbol)
        timeframe = self._normalize_timeframe(self.timeframe)

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)

        timestamp = self._normalize_datetime(self.timestamp)
        object.__setattr__(self, "timestamp", timestamp)

        open_price = Decimal(str(self.open))
        high_price = Decimal(str(self.high))
        low_price = Decimal(str(self.low))
        close_price = Decimal(str(self.close))
        volume = Decimal(str(self.volume))

        object.__setattr__(self, "open", open_price)
        object.__setattr__(self, "high", high_price)
        object.__setattr__(self, "low", low_price)
        object.__setattr__(self, "close", close_price)
        object.__setattr__(self, "volume", volume)

        spread = Decimal(str(self.spread)) if self.spread is not None else None

        object.__setattr__(self, "spread", spread)

        for name, value in (
            ("open", open_price),
            ("high", high_price),
            ("low", low_price),
            ("close", close_price),
        ):
            if value <= Decimal("0"):
                raise BacktestDataValidationError(
                    f"Candle {name} must be greater than zero."
                )

        if high_price < max(open_price, close_price):
            raise BacktestDataValidationError(
                "Candle high cannot be below open or close."
            )

        if low_price > min(open_price, close_price):
            raise BacktestDataValidationError(
                "Candle low cannot be above open or close."
            )

        if low_price > high_price:
            raise BacktestDataValidationError("Candle low cannot be greater than high.")

        if volume < Decimal("0"):
            raise BacktestDataValidationError("Candle volume cannot be negative.")

        if spread is not None and spread < Decimal("0"):
            raise BacktestDataValidationError("Candle spread cannot be negative.")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()

        if not normalized:
            raise BacktestDataValidationError("Candle symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        normalized = str(timeframe).strip().upper()

        if not normalized:
            raise BacktestDataValidationError("Candle timeframe cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class BacktestMarket:
    """
    Current simulated market state consumed by the execution/fill layer.

    The historical candle remains the primary source of OHLC data.

    ``bid`` and ``ask`` are optional because a pure OHLC backtest may
    not have a contemporaneous quote. When they are available, the
    fill engine can use them directly for market-order execution.
    """

    candle: BacktestCandle

    bid: Decimal | None = None
    ask: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candle, BacktestCandle):
            raise BacktestDataValidationError(
                "BacktestMarket requires a BacktestCandle."
            )

        bid = Decimal(str(self.bid)) if self.bid is not None else None

        ask = Decimal(str(self.ask)) if self.ask is not None else None

        if (bid is None) != (ask is None):
            raise BacktestDataValidationError(
                "Bid and ask must either both be provided or both be omitted."
            )

        if bid is not None and bid <= Decimal("0"):
            raise BacktestDataValidationError("Market bid must be greater than zero.")

        if ask is not None and ask <= Decimal("0"):
            raise BacktestDataValidationError("Market ask must be greater than zero.")

        if bid is not None and ask is not None and ask < bid:
            raise BacktestDataValidationError("Market ask cannot be below bid.")

        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)

    @property
    def symbol(self) -> str:
        """Normalized market symbol."""

        return self.candle.symbol

    @property
    def timeframe(self) -> str:
        """Normalized market timeframe."""

        return self.candle.timeframe

    @property
    def timestamp(self) -> datetime:
        """Current market timestamp."""

        return self.candle.timestamp

    @property
    def open(self) -> Decimal:
        return self.candle.open

    @property
    def high(self) -> Decimal:
        return self.candle.high

    @property
    def low(self) -> Decimal:
        return self.candle.low

    @property
    def close(self) -> Decimal:
        return self.candle.close

    @property
    def volume(self) -> Decimal:
        return self.candle.volume

    @property
    def spread(self) -> Decimal | None:
        return self.candle.spread

    @property
    def mid(self) -> Decimal:
        """
        Return the best available mid/reference price.

        Explicit bid/ask take precedence. Otherwise the candle close
        is used as the market reference.
        """

        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / Decimal("2")

        return self.close


@dataclass(frozen=True, slots=True)
class BacktestMarketEvent:
    """
    Single chronological market event.

    Candles are currently the supported event type. The wrapper keeps
    the engine extensible for future tick/replay event types without
    changing the main event-processing architecture.
    """

    event_type: MarketEventType
    candle: BacktestCandle

    @property
    def timestamp(self) -> datetime:
        return self.candle.timestamp

    @property
    def symbol(self) -> str:
        return self.candle.symbol

    @property
    def timeframe(self) -> str:
        return self.candle.timeframe

    @property
    def market(self) -> BacktestMarket:
        """
        Build the current market snapshot for this event.

        Historical candle data does not imply a separate live quote,
        so bid/ask remain unset here unless the caller constructs a
        richer BacktestMarket directly.
        """

        return BacktestMarket(candle=self.candle)


class BacktestMarketData:
    """
    Historical market-data collection for a backtest.

    Responsibilities:
    - validate candles
    - organize candles by symbol/timeframe
    - provide chronological iteration
    - provide symbol/timeframe filtering
    - provide bounded historical ranges

    It does not:
    - execute orders
    - manage positions
    - perform risk checks
    - run strategies
    - persist data
    """

    def __init__(
        self,
        candles: Iterable[BacktestCandle] | None = None,
    ) -> None:
        self._candles: list[BacktestCandle] = []

        self._index: dict[
            tuple[str, str],
            list[BacktestCandle],
        ] = {}

        self._finalized = False

        if candles is not None:
            self.add_many(candles)

    # ------------------------------------------------------------------
    # DATA REGISTRATION
    # ------------------------------------------------------------------

    def add(
        self,
        candle: BacktestCandle,
    ) -> None:
        """
        Add one historical candle.

        Data is allowed to arrive unsorted during loading. Ordering
        and duplicate validation are performed by ``finalize()``.
        """

        if not isinstance(candle, BacktestCandle):
            raise BacktestDataValidationError(
                "BacktestMarketData accepts only BacktestCandle instances."
            )

        self._candles.append(candle)

        key = (
            candle.symbol,
            candle.timeframe,
        )

        self._index.setdefault(key, []).append(candle)

        self._finalized = False

    def add_many(
        self,
        candles: Iterable[BacktestCandle],
    ) -> None:
        for candle in candles:
            self.add(candle)

    # ------------------------------------------------------------------
    # NORMALIZATION / VALIDATION
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """
        Sort and validate all loaded historical data.

        Each symbol/timeframe series must have strictly increasing
        timestamps and therefore cannot contain duplicates.
        """

        self._candles.sort(
            key=lambda candle: (
                candle.timestamp,
                candle.symbol,
                candle.timeframe,
            )
        )

        for key, candles in self._index.items():
            candles.sort(key=lambda candle: candle.timestamp)

            self._validate_series(
                key=key,
                candles=candles,
            )

        self._finalized = True

    @property
    def finalized(self) -> bool:
        """Whether the market-data collection has been finalized."""

        return self._finalized

    def _validate_series(
        self,
        key: tuple[str, str],
        candles: Sequence[BacktestCandle],
    ) -> None:
        previous_timestamp: datetime | None = None

        for candle in candles:
            if previous_timestamp is not None:
                if candle.timestamp <= previous_timestamp:
                    symbol, timeframe = key

                    raise BacktestDataValidationError(
                        "Historical candles must have strictly "
                        "increasing timestamps for "
                        f"{symbol} {timeframe}. "
                        "Duplicate/out-of-order timestamp: "
                        f"{candle.timestamp.isoformat()}"
                    )

            previous_timestamp = candle.timestamp

    # ------------------------------------------------------------------
    # ITERATION
    # ------------------------------------------------------------------

    def events(
        self,
        *,
        symbols: set[str] | None = None,
        timeframes: set[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[BacktestMarketEvent]:
        """
        Iterate through historical candles chronologically.

        Range semantics are:

            start <= timestamp < end

        This makes the backtest range consistent with database queries
        and historical loaders using half-open intervals.

        Events from multiple symbols/timeframes are globally ordered by:

            timestamp
            symbol
            timeframe
        """

        normalized_symbols = self._normalize_symbols(symbols)
        normalized_timeframes = self._normalize_timeframes(timeframes)

        normalized_start = (
            self._normalize_datetime(start) if start is not None else None
        )

        normalized_end = self._normalize_datetime(end) if end is not None else None

        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start >= normalized_end
        ):
            raise ValueError("Backtest start time must be before end time.")

        for candle in self._candles:
            if normalized_symbols is not None:
                if candle.symbol not in normalized_symbols:
                    continue

            if normalized_timeframes is not None:
                if candle.timeframe not in normalized_timeframes:
                    continue

            if normalized_start is not None and candle.timestamp < normalized_start:
                continue

            if normalized_end is not None and candle.timestamp >= normalized_end:
                continue

            yield BacktestMarketEvent(
                event_type=MarketEventType.CANDLE,
                candle=candle,
            )

    # ------------------------------------------------------------------
    # SERIES ACCESS
    # ------------------------------------------------------------------

    def candles(
        self,
        symbol: str,
        timeframe: str,
    ) -> list[BacktestCandle]:
        """
        Return all candles for one symbol/timeframe pair.
        """

        key = (
            self._normalize_symbol(symbol),
            self._normalize_timeframe(timeframe),
        )

        return list(self._index.get(key, []))

    def first(
        self,
        symbol: str,
        timeframe: str,
    ) -> BacktestCandle | None:
        """
        Return the first candle for a symbol/timeframe series.
        """

        candles = self.candles(
            symbol=symbol,
            timeframe=timeframe,
        )

        return candles[0] if candles else None

    def last(
        self,
        symbol: str,
        timeframe: str,
    ) -> BacktestCandle | None:
        """
        Return the last candle for a symbol/timeframe series.
        """

        candles = self.candles(
            symbol=symbol,
            timeframe=timeframe,
        )

        return candles[-1] if candles else None

    def count(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> int:
        """
        Count candles using optional symbol/timeframe filters.
        """

        if symbol is None and timeframe is None:
            return len(self._candles)

        normalized_symbol = (
            self._normalize_symbol(symbol) if symbol is not None else None
        )

        normalized_timeframe = (
            self._normalize_timeframe(timeframe) if timeframe is not None else None
        )

        return sum(
            1
            for candle in self._candles
            if (normalized_symbol is None or candle.symbol == normalized_symbol)
            and (
                normalized_timeframe is None or candle.timeframe == normalized_timeframe
            )
        )

    # ------------------------------------------------------------------
    # METADATA
    # ------------------------------------------------------------------

    @property
    def symbols(self) -> list[str]:
        """All symbols represented in the dataset."""

        return sorted({candle.symbol for candle in self._candles})

    @property
    def timeframes(self) -> list[str]:
        """All timeframes represented in the dataset."""

        return sorted({candle.timeframe for candle in self._candles})

    @property
    def series(self) -> list[tuple[str, str]]:
        """
        All available symbol/timeframe series.
        """

        return sorted(self._index)

    @property
    def start_time(self) -> datetime | None:
        """Earliest candle timestamp in the dataset."""

        if not self._candles:
            return None

        return min(candle.timestamp for candle in self._candles)

    @property
    def end_time(self) -> datetime | None:
        """Latest candle timestamp in the dataset."""

        if not self._candles:
            return None

        return max(candle.timestamp for candle in self._candles)

    # ------------------------------------------------------------------
    # RANGE
    # ------------------------------------------------------------------

    def range(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[BacktestCandle]:
        """
        Return a bounded historical series.

        Range semantics are:

            start <= timestamp < end
        """

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_timeframe = self._normalize_timeframe(timeframe)

        normalized_start = (
            self._normalize_datetime(start) if start is not None else None
        )

        normalized_end = self._normalize_datetime(end) if end is not None else None

        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start >= normalized_end
        ):
            raise ValueError("Range start must be before range end.")

        result: list[BacktestCandle] = []

        for candle in self._index.get(
            (normalized_symbol, normalized_timeframe),
            [],
        ):
            if normalized_start is not None and candle.timestamp < normalized_start:
                continue

            if normalized_end is not None and candle.timestamp >= normalized_end:
                continue

            result.append(candle)

        return result

    # ------------------------------------------------------------------
    # COVERAGE
    # ------------------------------------------------------------------

    def has_series(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Return whether a symbol/timeframe series exists.
        """

        key = (
            self._normalize_symbol(symbol),
            self._normalize_timeframe(timeframe),
        )

        return key in self._index and bool(self._index[key])

    def series_count(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> int:
        """
        Count distinct symbol/timeframe series matching the filters.
        """

        normalized_symbol = (
            self._normalize_symbol(symbol) if symbol is not None else None
        )

        normalized_timeframe = (
            self._normalize_timeframe(timeframe) if timeframe is not None else None
        )

        return sum(
            1
            for current_symbol, current_timeframe in self._index
            if (normalized_symbol is None or current_symbol == normalized_symbol)
            and (
                normalized_timeframe is None
                or current_timeframe == normalized_timeframe
            )
        )

    # ------------------------------------------------------------------
    # RESET / CLEAR
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all loaded market data."""

        self._candles.clear()
        self._index.clear()
        self._finalized = False

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def metadata(self) -> dict[str, Any]:
        """
        Return dataset-level metadata useful for diagnostics and
        backtest reporting.
        """

        return {
            "candle_count": len(self._candles),
            "series_count": len(self._index),
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "finalized": self._finalized,
        }

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        normalized = str(symbol).strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized

    @classmethod
    def _normalize_symbols(
        cls,
        symbols: set[str] | None,
    ) -> set[str] | None:
        if symbols is None:
            return None

        return {cls._normalize_symbol(symbol) for symbol in symbols}

    @staticmethod
    def _normalize_timeframe(
        timeframe: str,
    ) -> str:
        normalized = str(timeframe).strip().upper()

        if not normalized:
            raise ValueError("Timeframe cannot be empty.")

        return normalized

    @classmethod
    def _normalize_timeframes(
        cls,
        timeframes: set[str] | None,
    ) -> set[str] | None:
        if timeframes is None:
            return None

        return {cls._normalize_timeframe(timeframe) for timeframe in timeframes}

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
