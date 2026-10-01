from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5

from app.core.logging import logger


class MarketDataBroker:
    """
    Low-level broker responsible for retrieving market data
    directly from MetaTrader 5.

    This class does not handle authentication or business logic.

    Authentication is expected to be established by the MT5
    connection layer before market-data operations are used.
    """

    @staticmethod
    def _ensure_symbol_selected(symbol: str) -> bool:
        """
        Ensure the MT5 symbol exists and is visible/selected.
        """

        info = mt5.symbol_info(symbol)

        if info is None:
            logger.warning(
                "Symbol not found in MT5: %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return False

        if not info.visible:
            selected = mt5.symbol_select(symbol, True)

            if not selected:
                logger.error(
                    "Failed to select symbol %s: last_error=%s",
                    symbol,
                    mt5.last_error(),
                )
                return False

            logger.info(
                "Selected MT5 symbol: %s",
                symbol,
            )

        return True

    @staticmethod
    def _normalize_utc(value: datetime | None) -> datetime | None:
        """
        Normalize a datetime to an explicit UTC-aware datetime.

        MT5's Python API expects historical datetime values to be
        interpreted in UTC.
        """

        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_tick(symbol: str, tick: Any) -> bool:
        """
        Validate a raw MT5 tick before it is allowed into AQE.

        MT5 can return a tick structure containing zero/default
        values when usable market data is not actually available.

        Such ticks must never be published to Redis.
        """

        if tick is None:
            logger.warning(
                "MT5 returned no tick for %s: last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return False

        try:
            data = tick._asdict()
        except AttributeError:
            logger.error(
                "Invalid MT5 tick object for %s: %r",
                symbol,
                tick,
            )
            return False

        timestamp = data.get("time")
        bid = data.get("bid")
        ask = data.get("ask")

        try:
            timestamp_value = int(timestamp or 0)
            bid_value = float(bid or 0.0)
            ask_value = float(ask or 0.0)
        except (TypeError, ValueError):
            logger.error(
                "Invalid MT5 tick values for %s: %r",
                symbol,
                data,
            )
            return False

        if timestamp_value <= 0:
            logger.warning(
                "Rejected MT5 tick for %s: invalid timestamp=%r "
                "raw_tick=%r last_error=%s",
                symbol,
                timestamp,
                data,
                mt5.last_error(),
            )
            return False

        if bid_value <= 0:
            logger.warning(
                "Rejected MT5 tick for %s: invalid bid=%r "
                "raw_tick=%r last_error=%s",
                symbol,
                bid,
                data,
                mt5.last_error(),
            )
            return False

        if ask_value <= 0:
            logger.warning(
                "Rejected MT5 tick for %s: invalid ask=%r "
                "raw_tick=%r last_error=%s",
                symbol,
                ask,
                data,
                mt5.last_error(),
            )
            return False

        if ask_value < bid_value:
            logger.warning(
                "Rejected MT5 tick for %s: ask=%s < bid=%s "
                "raw_tick=%r last_error=%s",
                symbol,
                ask_value,
                bid_value,
                data,
                mt5.last_error(),
            )
            return False

        return True

    @staticmethod
    def get_tick(symbol: str):
        """
        Retrieve the latest valid tick for a symbol.

        Invalid or empty MT5 ticks are rejected and never returned
        to the application layer.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve tick: empty symbol.",
            )
            return None

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        tick = mt5.symbol_info_tick(symbol)

        if not MarketDataBroker._validate_tick(symbol, tick):
            return None

        return tick

    @staticmethod
    def get_candles(
        symbol: str,
        timeframe: int,
        count: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        """
        Retrieve historical OHLCV candles directly from MT5.

        Range mode:
            When either `start` or `end` is supplied,
            `mt5.copy_rates_range()` is used.

        Latest-N mode:
            When neither `start` nor `end` is supplied,
            `mt5.copy_rates_from_pos()` is used.

        Returns:
            MT5 NumPy structured array when candles are available.
            None when MT5 cannot retrieve the requested data.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve candles: empty symbol.",
            )
            return None

        # ------------------------------------------------------------------
        # Verify MT5 terminal state.
        # ------------------------------------------------------------------

        terminal = mt5.terminal_info()

        if terminal is None:
            logger.error(
                "MT5 terminal information unavailable while retrieving "
                "candles for %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        if not terminal.connected:
            logger.error(
                "MT5 terminal is not connected while retrieving candles "
                "for %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        # ------------------------------------------------------------------
        # Ensure the requested symbol is available.
        # ------------------------------------------------------------------

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        symbol_info = mt5.symbol_info(symbol)

        if symbol_info is None:
            logger.error(
                "MT5 symbol disappeared after selection: %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        # ------------------------------------------------------------------
        # Normalize datetime values.
        # ------------------------------------------------------------------

        start = MarketDataBroker._normalize_utc(start)
        end = MarketDataBroker._normalize_utc(end)

        # ------------------------------------------------------------------
        # Validate range.
        # ------------------------------------------------------------------

        if start is not None and end is not None and start > end:
            logger.warning(
                "Invalid candle range for %s: start=%s is later than end=%s",
                symbol,
                start,
                end,
            )
            return None

        # ------------------------------------------------------------------
        # Range-based historical retrieval.
        # ------------------------------------------------------------------

        if start is not None or end is not None:
            if start is None:
                start = end

            if end is None:
                end = datetime.now(timezone.utc)

            logger.info(
                "Requesting MT5 historical candles | "
                "symbol=%s | timeframe=%s | start=%s | end=%s",
                symbol,
                timeframe,
                start.isoformat(),
                end.isoformat(),
            )

            rates = mt5.copy_rates_range(
                symbol,
                timeframe,
                start,
                end,
            )

            last_error = mt5.last_error()

            if rates is None:
                logger.error(
                    "MT5 copy_rates_range returned None | "
                    "symbol=%s | timeframe=%s | start=%s | end=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    start.isoformat(),
                    end.isoformat(),
                    last_error,
                )
                return None

            try:
                rate_count = len(rates)
            except TypeError:
                logger.error(
                    "MT5 returned an unexpected candle result | "
                    "symbol=%s | result=%r | last_error=%s",
                    symbol,
                    rates,
                    last_error,
                )
                return None

            if rate_count == 0:
                logger.warning(
                    "MT5 returned zero historical candles | "
                    "symbol=%s | timeframe=%s | start=%s | end=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    start.isoformat(),
                    end.isoformat(),
                    last_error,
                )
                return None

            if count is not None:
                if count < 1:
                    logger.warning(
                        "Invalid candle count for %s: %s",
                        symbol,
                        count,
                    )
                    return None

                if rate_count > count:
                    rates = rates[-count:]

            logger.info(
                "MT5 historical candles retrieved | "
                "symbol=%s | timeframe=%s | count=%s | start=%s | end=%s",
                symbol,
                timeframe,
                len(rates),
                start.isoformat(),
                end.isoformat(),
            )

            return rates

        # ------------------------------------------------------------------
        # Latest-N retrieval.
        # ------------------------------------------------------------------

        if count is None:
            count = 100

        if count < 1:
            logger.warning(
                "Invalid candle count for %s: %s",
                symbol,
                count,
            )
            return None

        logger.info(
            "Requesting latest MT5 candles | "
            "symbol=%s | timeframe=%s | count=%s",
            symbol,
            timeframe,
            count,
        )

        rates = mt5.copy_rates_from_pos(
            symbol,
            timeframe,
            0,
            count,
        )

        last_error = mt5.last_error()

        if rates is None:
            logger.error(
                "MT5 copy_rates_from_pos returned None | "
                "symbol=%s | timeframe=%s | count=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                count,
                last_error,
            )
            return None

        try:
            rate_count = len(rates)
        except TypeError:
            logger.error(
                "MT5 returned an unexpected candle result | "
                "symbol=%s | result=%r | last_error=%s",
                symbol,
                rates,
                last_error,
            )
            return None

        if rate_count == 0:
            logger.warning(
                "MT5 returned zero latest candles | "
                "symbol=%s | timeframe=%s | count=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                count,
                last_error,
            )
            return None

        logger.info(
            "Latest MT5 candles retrieved | "
            "symbol=%s | timeframe=%s | count=%s",
            symbol,
            timeframe,
            rate_count,
        )

        return rates