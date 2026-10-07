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

    Return semantics for candle retrieval:

        None:
            The request could not be fulfilled because of an invalid
            request, unavailable terminal, unavailable symbol, invalid
            parameters, or an MT5 retrieval failure.

        Empty NumPy array:
            The request itself was valid, but MT5 has no candles for
            the requested interval.

        Non-empty NumPy array:
            Historical candles were successfully retrieved.
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
    def _timestamp_to_utc(timestamp: Any) -> datetime | None:
        """
        Convert an MT5 Unix timestamp into a UTC datetime.

        Returns None when the timestamp cannot be converted.
        """

        try:
            timestamp_value = int(timestamp)
        except (TypeError, ValueError, OverflowError):
            return None

        if timestamp_value <= 0:
            return None

        try:
            return datetime.fromtimestamp(
                timestamp_value,
                tz=timezone.utc,
            )
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _describe_candle(rate: Any) -> dict[str, Any]:
        """
        Extract useful diagnostic information from an MT5 candle.

        This method is intentionally defensive because MT5 returns
        NumPy structured-array records rather than normal dictionaries.
        """

        try:
            timestamp = rate["time"]
        except (KeyError, IndexError, TypeError):
            timestamp = None

        timestamp_utc = MarketDataBroker._timestamp_to_utc(timestamp)

        description: dict[str, Any] = {
            "timestamp": (
                int(timestamp) if timestamp is not None else None
            ),
            "timestamp_utc": (
                timestamp_utc.isoformat()
                if timestamp_utc is not None
                else None
            ),
        }

        for field in (
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "real_volume",
            "spread",
        ):
            try:
                value = rate[field]
            except (KeyError, IndexError, TypeError):
                continue

            try:
                if hasattr(value, "item"):
                    value = value.item()
            except Exception:
                pass

            description[field] = value

        return description

    @staticmethod
    def _log_range_result(
        *,
        symbol: str,
        timeframe: int,
        requested_start: datetime,
        requested_end: datetime,
        rates: Any,
        last_error: Any,
    ) -> None:
        """
        Log detailed diagnostics for a historical MT5 range response.

        This is particularly useful for diagnosing cases where MT5
        returns a very small number of candles for a large requested
        historical range.
        """

        try:
            rate_count = len(rates)
        except TypeError:
            logger.error(
                "Unable to inspect MT5 historical result | "
                "symbol=%s | timeframe=%s | result=%r | "
                "last_error=%s",
                symbol,
                timeframe,
                rates,
                last_error,
            )
            return

        if rate_count == 0:
            logger.warning(
                "MT5 historical range returned zero candles | "
                "symbol=%s | timeframe=%s | "
                "requested_start=%s | requested_end=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                requested_start.isoformat(),
                requested_end.isoformat(),
                last_error,
            )
            return

        first_candle = MarketDataBroker._describe_candle(
            rates[0],
        )
        last_candle = MarketDataBroker._describe_candle(
            rates[-1],
        )

        first_timestamp = first_candle.get("timestamp")
        last_timestamp = last_candle.get("timestamp")

        first_datetime = MarketDataBroker._timestamp_to_utc(
            first_timestamp,
        )
        last_datetime = MarketDataBroker._timestamp_to_utc(
            last_timestamp,
        )

        returned_span_seconds: float | None = None

        if first_datetime is not None and last_datetime is not None:
            returned_span_seconds = (
                last_datetime - first_datetime
            ).total_seconds()

        requested_span_seconds = (
            requested_end - requested_start
        ).total_seconds()

        logger.info(
            "MT5 historical range diagnostics | "
            "symbol=%s | timeframe=%s | "
            "requested_start=%s | requested_end=%s | "
            "requested_span_seconds=%s | "
            "returned_count=%s | "
            "first_timestamp=%s | "
            "first_timestamp_utc=%s | "
            "last_timestamp=%s | "
            "last_timestamp_utc=%s | "
            "returned_span_seconds=%s | "
            "last_error=%s",
            symbol,
            timeframe,
            requested_start.isoformat(),
            requested_end.isoformat(),
            requested_span_seconds,
            rate_count,
            first_timestamp,
            first_candle.get("timestamp_utc"),
            last_timestamp,
            last_candle.get("timestamp_utc"),
            returned_span_seconds,
            last_error,
        )

        logger.info(
            "MT5 first historical candle | "
            "symbol=%s | timeframe=%s | candle=%s",
            symbol,
            timeframe,
            first_candle,
        )

        logger.info(
            "MT5 last historical candle | "
            "symbol=%s | timeframe=%s | candle=%s",
            symbol,
            timeframe,
            last_candle,
        )

        if rate_count == 1:
            logger.warning(
                "MT5 returned ONLY ONE candle for a historical range | "
                "symbol=%s | timeframe=%s | "
                "requested_start=%s | requested_end=%s | "
                "returned_candle=%s | last_error=%s",
                symbol,
                timeframe,
                requested_start.isoformat(),
                requested_end.isoformat(),
                first_candle,
                last_error,
            )

        elif (
            first_datetime is not None
            and last_datetime is not None
            and requested_span_seconds > 0
            and returned_span_seconds is not None
            and returned_span_seconds < requested_span_seconds * 0.01
        ):
            logger.warning(
                "MT5 returned unusually sparse historical data | "
                "symbol=%s | timeframe=%s | "
                "requested_span_seconds=%s | "
                "returned_span_seconds=%s | "
                "returned_count=%s | "
                "first=%s | last=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                requested_span_seconds,
                returned_span_seconds,
                rate_count,
                first_candle.get("timestamp_utc"),
                last_candle.get("timestamp_utc"),
                last_error,
            )

    @staticmethod
    def _validate_tick(
        symbol: str,
        tick: Any,
    ) -> bool:
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

        if not MarketDataBroker._validate_tick(
            symbol,
            tick,
        ):
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

            Empty MT5 NumPy structured array when the request is valid
            but no candles exist for the requested interval.

            None when MT5 cannot fulfill the request or the request
            itself is invalid.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve candles: empty symbol.",
            )
            return None

        # --------------------------------------------------------------
        # Verify MT5 terminal state.
        # --------------------------------------------------------------

        terminal = mt5.terminal_info()

        if terminal is None:
            logger.error(
                "MT5 terminal information unavailable while "
                "retrieving candles for %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        if not terminal.connected:
            logger.error(
                "MT5 terminal is not connected while retrieving "
                "candles for %s | last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        # --------------------------------------------------------------
        # Ensure the requested symbol is available.
        # --------------------------------------------------------------

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        symbol_info = mt5.symbol_info(symbol)

        if symbol_info is None:
            logger.error(
                "MT5 symbol disappeared after selection: %s | "
                "last_error=%s",
                symbol,
                mt5.last_error(),
            )
            return None

        _ = symbol_info

        # --------------------------------------------------------------
        # Normalize datetime values.
        # --------------------------------------------------------------

        start = MarketDataBroker._normalize_utc(start)
        end = MarketDataBroker._normalize_utc(end)

        # --------------------------------------------------------------
        # Validate range.
        # --------------------------------------------------------------

        if start is not None and end is not None and start > end:
            logger.warning(
                "Invalid candle range for %s: start=%s is later "
                "than end=%s",
                symbol,
                start,
                end,
            )
            return None

        # --------------------------------------------------------------
        # Range-based historical retrieval.
        # --------------------------------------------------------------

        if start is not None or end is not None:
            if start is None:
                start = end

            if end is None:
                end = datetime.now(timezone.utc)

            requested_start = start
            requested_end = end

            logger.info(
                "Requesting MT5 historical candles | "
                "symbol=%s | timeframe=%s | start=%s | end=%s",
                symbol,
                timeframe,
                requested_start.isoformat(),
                requested_end.isoformat(),
            )

            rates = mt5.copy_rates_range(
                symbol,
                timeframe,
                requested_start,
                requested_end,
            )

            last_error = mt5.last_error()

            # ----------------------------------------------------------
            # None means the MT5 request itself failed.
            # ----------------------------------------------------------

            if rates is None:
                logger.error(
                    "MT5 copy_rates_range returned None | "
                    "symbol=%s | timeframe=%s | start=%s | end=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
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

            # ----------------------------------------------------------
            # Empty array means the request succeeded, but there are
            # simply no candles in the requested interval.
            #
            # This is normal for weekends, market closures, session
            # breaks, holidays, or symbols that do not trade during
            # the requested period.
            # ----------------------------------------------------------

            if rate_count == 0:
                logger.info(
                    "MT5 returned zero historical candles for valid "
                    "request | symbol=%s | timeframe=%s | "
                    "start=%s | end=%s | last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    last_error,
                )

                MarketDataBroker._log_range_result(
                    symbol=symbol,
                    timeframe=timeframe,
                    requested_start=requested_start,
                    requested_end=requested_end,
                    rates=rates,
                    last_error=last_error,
                )

                return rates

            # ----------------------------------------------------------
            # Detailed diagnostics BEFORE applying the optional count
            # limit.
            # ----------------------------------------------------------

            MarketDataBroker._log_range_result(
                symbol=symbol,
                timeframe=timeframe,
                requested_start=requested_start,
                requested_end=requested_end,
                rates=rates,
                last_error=last_error,
            )

            # ----------------------------------------------------------
            # Optional range-result limit.
            # ----------------------------------------------------------

            if count is not None:
                if count < 1:
                    logger.warning(
                        "Invalid candle count for %s: %s",
                        symbol,
                        count,
                    )
                    return None

                if rate_count > count:
                    logger.debug(
                        "Limiting MT5 historical result | "
                        "symbol=%s | timeframe=%s | "
                        "original_count=%s | requested_count=%s",
                        symbol,
                        timeframe,
                        rate_count,
                        count,
                    )
                    rates = rates[-count:]

            logger.info(
                "MT5 historical candles retrieved | "
                "symbol=%s | timeframe=%s | count=%s | "
                "start=%s | end=%s | last_error=%s",
                symbol,
                timeframe,
                len(rates),
                requested_start.isoformat(),
                requested_end.isoformat(),
                last_error,
            )

            return rates

        # --------------------------------------------------------------
        # Latest-N retrieval.
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # A valid latest-N query with no available candles is also
        # represented by an empty array rather than None.
        # --------------------------------------------------------------

        if rate_count == 0:
            logger.info(
                "MT5 returned zero latest candles for valid request | "
                "symbol=%s | timeframe=%s | count=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                count,
                last_error,
            )
            return rates

        first_candle = MarketDataBroker._describe_candle(
            rates[0],
        )
        last_candle = MarketDataBroker._describe_candle(
            rates[-1],
        )

        logger.info(
            "Latest MT5 candles retrieved | "
            "symbol=%s | timeframe=%s | count=%s | "
            "first=%s | last=%s | last_error=%s",
            symbol,
            timeframe,
            rate_count,
            first_candle.get("timestamp_utc"),
            last_candle.get("timestamp_utc"),
            last_error,
        )

        return rates