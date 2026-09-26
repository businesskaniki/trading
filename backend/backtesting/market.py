from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Iterable, Iterator, Sequence


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

    The backtesting subsystem intentionally owns this lightweight
    representation rather than coupling the core backtest loop to
    a particular persistence model.
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
        symbol = self.symbol.strip().upper()
        timeframe = self.timeframe.strip().upper()

        if not symbol:
            raise BacktestDataValidationError("Candle symbol cannot be empty.")

        if not timeframe:
            raise BacktestDataValidationError("Candle timeframe cannot be empty.")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)

        timestamp = self.timestamp

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        object.__setattr__(self, "timestamp", timestamp)

        for name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            if value <= Decimal("0"):
                raise BacktestDataValidationError(
                    f"Candle {name} must be greater than zero."
                )

        if self.high < max(self.open, self.close):
            raise BacktestDataValidationError(
                "Candle high cannot be below open or close."
            )

        if self.low > min(self.open, self.close):
            raise BacktestDataValidationError(
                "Candle low cannot be above open or close."
            )

        if self.volume < Decimal("0"):
            raise BacktestDataValidationError("Candle volume cannot be negative.")

        if self.spread is not None and self.spread < Decimal("0"):
            raise BacktestDataValidationError("Candle spread cannot be negative.")


@dataclass(frozen=True, slots=True)
class BacktestMarketEvent:
    """
    A single chronological market event.

    Currently the backtest engine processes candles. The event wrapper
    leaves room for tick/replay events later without changing the
    overall engine architecture.
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

        if candles is not None:
            self.add_many(candles)

    # ------------------------------------------------------------------
    # DATA REGISTRATION
    # ------------------------------------------------------------------

    def add(self, candle: BacktestCandle) -> None:
        self._candles.append(candle)

        key = (
            candle.symbol,
            candle.timeframe,
        )

        self._index.setdefault(key, []).append(candle)

    def add_many(
        self,
        candles: Iterable[BacktestCandle],
    ) -> None:
        for candle in candles:
            self.add(candle)

    # ------------------------------------------------------------------
    # NORMALIZATION
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """
        Sort and validate the loaded historical data.

        This should be called before starting a backtest.
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
                        f"Duplicate/out-of-order timestamp: "
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

        The returned sequence is globally chronological across all
        selected symbols.

        Example:

            09:00 XAUUSD
            09:00 BTCUSD
            09:15 XAUUSD
            09:15 BTCUSD
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
        return sorted({candle.symbol for candle in self._candles})

    @property
    def timeframes(self) -> list[str]:
        return sorted({candle.timeframe for candle in self._candles})

    @property
    def start_time(self) -> datetime | None:
        if not self._candles:
            return None

        return min(candle.timestamp for candle in self._candles)

    @property
    def end_time(self) -> datetime | None:
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
    # RESET / CLEAR
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._candles.clear()
        self._index.clear()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        normalized = symbol.strip().upper()

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
        normalized = timeframe.strip().upper()

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
