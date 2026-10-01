from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from strategies.core.context import MarketDataView

from .market import BacktestCandle, BacktestMarketData


class BacktestMarketDataView(MarketDataView):
    """
    Strategy-facing market-data view for backtests.

    This adapter exposes BacktestMarketData through the Strategy Core's
    MarketDataView contract without coupling Strategy Core to the
    backtesting subsystem.

    The view is simulation-time aware:

        Strategy
            |
            v
        BacktestMarketDataView
            |
            v
        BacktestMarketData

    A strategy can never see a candle whose timestamp is later than
    the current simulation clock.

    The view contains no order, broker, portfolio, or risk logic.
    """

    def __init__(
        self,
        market_data: BacktestMarketData,
        *,
        current_time: datetime | None = None,
    ) -> None:
        if not isinstance(market_data, BacktestMarketData):
            raise TypeError("market_data must be a BacktestMarketData instance.")

        self._market_data = market_data

        self._current_time = self._normalize_datetime(
            current_time,
        )

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def market_data(self) -> BacktestMarketData:
        """
        Return the underlying immutable-facing historical data source.

        The BacktestMarketData object itself owns registration and
        validation. Strategies should normally use the MarketDataView
        methods rather than accessing it directly.
        """

        return self._market_data

    @property
    def current_time(self) -> datetime | None:
        """Return the current simulated market timestamp."""

        return self._current_time

    # ==================================================================
    # SIMULATION CLOCK
    # ==================================================================

    def set_current_time(
        self,
        timestamp: datetime,
    ) -> None:
        """
        Advance the simulation clock.

        Time is strictly monotonic. The strategy-facing view therefore
        cannot accidentally move backwards and expose an inconsistent
        historical state.
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

    def reset_clock(self) -> None:
        """
        Reset the simulation clock.

        After reset, no market data is exposed until the next
        ``set_current_time()`` call. This prevents accidental exposure
        of future historical data.
        """

        self._current_time = None

    # ==================================================================
    # MARKET DATA VIEW
    # ==================================================================

    async def get_latest_tick(
        self,
        symbol: str,
    ) -> Any | None:
        """
        Return the latest visible tick for a symbol.

        BacktestMarketData currently contains candle data only.
        No synthetic tick is generated because doing so would create
        artificial market information.

        Returns:
            None
        """

        # Intentionally no synthetic tick generation.
        return None

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list[BacktestCandle]:
        """
        Return the latest candles visible to the strategy.

        Only candles satisfying:

            candle.timestamp <= current_time

        are exposed.

        When the simulation clock has not started, an empty result is
        returned rather than exposing the complete historical dataset.
        """

        if count <= 0:
            return []

        if self._current_time is None:
            return []

        candles = self._market_data.candles(
            symbol=symbol,
            timeframe=timeframe,
        )

        if not candles:
            return []

        visible = [
            candle for candle in candles if candle.timestamp <= self._current_time
        ]

        if not visible:
            return []

        return visible[-count:]

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[BacktestCandle]:
        """
        Return historical candles within a bounded range.

        The requested range uses:

            start <= timestamp < end

        and the result is additionally restricted to the current
        simulation clock.

        Therefore a strategy can never request a historical range and
        accidentally obtain future candles.
        """

        normalized_start = self._normalize_datetime(start)
        normalized_end = self._normalize_datetime(end)

        if normalized_start is None:
            raise ValueError("Historical candle start timestamp is required.")

        if normalized_end is None:
            raise ValueError("Historical candle end timestamp is required.")

        if normalized_start >= normalized_end:
            raise ValueError("Historical candle start must be before end.")

        # Before the simulation begins there is no strategy-visible
        # market state.
        if self._current_time is None:
            return []

        # The effective upper bound is the earlier of:
        #
        #   requested end
        #   current simulation time + one microsecond
        #
        # Since BacktestMarketData.range() uses an exclusive end bound,
        # adding one microsecond allows the candle exactly at
        # current_time to remain visible.
        effective_end = min(
            normalized_end,
            self._current_time,
        )

        # If the simulation clock is before the requested range, there
        # is no visible data.
        if effective_end < normalized_start:
            return []

        candles = self._market_data.range(
            symbol=symbol,
            timeframe=timeframe,
            start=normalized_start,
            end=effective_end,
        )

        # ``range`` uses an exclusive end boundary. A strategy should
        # still be able to see the candle occurring exactly at the
        # current simulation timestamp.
        if effective_end == self._current_time and self._current_time is not None:
            current_candle = None

            for candidate in self._market_data.candles(
                symbol=symbol,
                timeframe=timeframe,
            ):
                if candidate.timestamp == self._current_time:
                    current_candle = candidate
                    break

            if current_candle is not None:
                if normalized_start <= current_candle.timestamp < normalized_end:
                    if not any(
                        candle.timestamp == current_candle.timestamp
                        for candle in candles
                    ):
                        candles.append(current_candle)

        candles.sort(
            key=lambda candle: candle.timestamp,
        )

        return candles

    # ==================================================================
    # ADDITIONAL BACKTEST HELPERS
    # ==================================================================

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> BacktestCandle | None:
        """
        Return the latest candle visible to the strategy.

        This convenience method is useful for strategies that need
        one current candle rather than a full lookback window.
        """

        candles = await self.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=1,
        )

        return candles[-1] if candles else None

    async def has_visible_data(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """
        Return whether at least one candle is visible at the current
        simulation time.
        """

        if self._current_time is None:
            return False

        candle = await self.get_latest_candle(
            symbol=symbol,
            timeframe=timeframe,
        )

        return candle is not None

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
