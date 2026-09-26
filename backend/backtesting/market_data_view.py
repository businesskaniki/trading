from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from strategies.core.context import MarketDataView

from .market import BacktestCandle, BacktestMarketData


class BacktestMarketDataView(MarketDataView):
    """
    Strategy-facing market-data view for backtests.

    This adapter exposes BacktestMarketData through the Strategy Core's
    MarketDataView protocol without coupling Strategy Core to the
    backtesting subsystem.

    The view is simulation-time aware. Strategies can only see candles
    at or before the current simulation timestamp, preventing
    look-ahead bias.
    """

    def __init__(
        self,
        market_data: BacktestMarketData,
        *,
        current_time: datetime | None = None,
    ) -> None:
        self._market_data = market_data
        self._current_time = self._normalize_datetime(current_time)

    # ==================================================================
    # SIMULATION CLOCK
    # ==================================================================

    @property
    def current_time(self) -> datetime | None:
        """Return the current simulated market time."""

        return self._current_time

    def set_current_time(
        self,
        timestamp: datetime,
    ) -> None:
        """
        Advance the strategy-facing simulation clock.

        The clock is monotonic. A backtest event must never move the
        strategy view backwards in time.
        """

        normalized = self._normalize_datetime(timestamp)

        if normalized is None:
            raise ValueError("Simulation timestamp cannot be None.")

        if self._current_time is not None and normalized < self._current_time:
            raise ValueError(
                "Backtest market-data time cannot move backwards. "
                f"Current={self._current_time.isoformat()}, "
                f"requested={normalized.isoformat()}."
            )

        self._current_time = normalized

    # ==================================================================
    # MARKET DATA VIEW
    # ==================================================================

    async def get_latest_tick(
        self,
        symbol: str,
    ) -> Any | None:
        """
        Return the latest tick available to the strategy.

        BacktestMarketData currently contains candles only, so no
        synthetic tick is generated.
        """

        return None

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list[BacktestCandle]:
        """
        Return the latest `count` candles visible at simulation time.

        Candles after the current simulation timestamp are never exposed.
        """

        if count <= 0:
            return []

        candles = self._market_data.candles(
            symbol=symbol,
            timeframe=timeframe,
        )

        if self._current_time is None:
            return candles[-count:]

        visible = [
            candle for candle in candles if candle.timestamp <= self._current_time
        ]

        return visible[-count:]

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[BacktestCandle]:
        """
        Return historical candles within the requested range while
        respecting the current simulation timestamp.
        """

        normalized_start = self._normalize_datetime(start)
        normalized_end = self._normalize_datetime(end)

        if normalized_start is None or normalized_end is None:
            raise ValueError("Historical candle start and end timestamps are required.")

        if normalized_start >= normalized_end:
            raise ValueError("Historical candle start must be before end.")

        candles = self._market_data.range(
            symbol=symbol,
            timeframe=timeframe,
            start=normalized_start,
            end=normalized_end,
        )

        if self._current_time is None:
            return candles

        return [candle for candle in candles if candle.timestamp <= self._current_time]

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _normalize_datetime(
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
