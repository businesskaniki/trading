from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5

from app.broker.mt5_lock import mt5_synchronized
from app.core.logging import logger


class MarketDataBroker:
    """
    Low-level broker responsible for retrieving market data
    directly from MetaTrader 5.

    Authentication and connection recovery belong to the connection
    layer. HTTP response handling belongs to the API route layer.

    Return semantics for candle retrieval:

        None:
            The request could not be completed because the terminal
            is unavailable, the symbol or parameters are invalid,
            or MT5 reported a retrieval failure.

        Empty NumPy array:
            MT5 accepted the request but returned no valid candles
            for the requested interval.

        Non-empty NumPy array:
            Historical candles were retrieved successfully.

    All complete tick and candle retrieval operations are protected
    by the process-wide MT5 API lock.
    """

    CONNECTION_ERROR_CODES = {
        -10001,
        -10002,
        -10003,
        -10004,
        -10005,
    }

    # =========================================================
    # ERROR HELPERS
    # =========================================================

    @staticmethod
    def _last_error() -> Any:
        """Capture the latest MT5 error defensively."""
        try:
            return mt5.last_error()
        except Exception:
            return None

    @classmethod
    def _is_connection_error(cls, error: Any) -> bool:
        """Identify common MT5 IPC and internal connection errors."""
        if isinstance(error, (tuple, list)) and error:
            try:
                if int(error[0]) in cls.CONNECTION_ERROR_CODES:
                    return True
            except (TypeError, ValueError, OverflowError):
                pass

        message = str(error).lower()

        indicators = (
            "no ipc connection",
            "ipc connection",
            "internal fail connect",
            "internal fail send",
            "internal fail receive",
            "internal fail timeout",
        )

        return any(indicator in message for indicator in indicators)

    @staticmethod
    def _terminal_ready() -> bool:
        """
        Check whether the MT5 terminal is available and connected.

        This method does not perform reconnection. Calls made from
        get_tick() and get_candles() already hold the shared MT5 lock.
        """
        try:
            terminal = mt5.terminal_info()

            if terminal is None:
                logger.error(
                    "MT5 terminal information is unavailable | " "last_error=%s",
                    MarketDataBroker._last_error(),
                )
                return False

            if not bool(getattr(terminal, "connected", False)):
                logger.warning(
                    "MT5 terminal is not connected to the broker | " "last_error=%s",
                    MarketDataBroker._last_error(),
                )
                return False

            return True

        except Exception:
            logger.exception("Failed to inspect MT5 terminal readiness.")
            return False

    # =========================================================
    # SYMBOL SELECTION
    # =========================================================

    @staticmethod
    def _ensure_symbol_selected(symbol: str) -> bool:
        """
        Ensure the MT5 symbol exists and is visible.

        The caller must hold MT5_API_LOCK for the complete operation.
        """
        try:
            info = mt5.symbol_info(symbol)

        except Exception:
            logger.exception(
                "MT5 symbol lookup raised an exception | " "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return False

        if info is None:
            logger.warning(
                "MT5 symbol lookup failed | " "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return False

        if not info.visible:
            try:
                selected = mt5.symbol_select(symbol, True)

            except Exception:
                logger.exception(
                    "MT5 symbol selection raised an exception | "
                    "symbol=%s | last_error=%s",
                    symbol,
                    MarketDataBroker._last_error(),
                )
                return False

            if not selected:
                logger.error(
                    "Failed to select MT5 symbol | " "symbol=%s | last_error=%s",
                    symbol,
                    MarketDataBroker._last_error(),
                )
                return False

            logger.info("Selected MT5 symbol: %s", symbol)

        return True

    # =========================================================
    # DATETIME HELPERS
    # =========================================================

    @staticmethod
    def _normalize_utc(
        value: datetime | None,
    ) -> datetime | None:
        """
        Normalize a datetime to an explicit UTC-aware datetime.

        MT5 historical range requests use UTC datetimes.
        """
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @staticmethod
    def _timestamp_to_utc(
        timestamp: Any,
    ) -> datetime | None:
        """Convert an MT5 Unix timestamp into a UTC datetime."""
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

    # =========================================================
    # CANDLE VALIDATION
    # =========================================================

    @staticmethod
    def _filter_rates_to_requested_range(
        *,
        symbol: str,
        timeframe: int,
        requested_start: datetime,
        requested_end: datetime,
        rates: Any,
        last_error: Any,
    ) -> Any | None:
        """
        Validate and filter a structured MT5 candle array.

        The requested interval is half-open:

            requested_start <= candle_timestamp < requested_end

        Returns:
            Filtered NumPy array:
                All candles have valid timestamps within the interval.
                The array may be empty if no candles qualify.

            None:
                The returned data cannot be safely validated.

        This method prevents MT5 candles from outside the requested
        historical interval from entering the AQE market-data pipeline.
        """
        try:
            dtype_names = getattr(
                getattr(rates, "dtype", None),
                "names",
                None,
            )

            if not dtype_names or "time" not in dtype_names:
                logger.error(
                    "MT5 returned candles without a usable time field; "
                    "rejecting the response | "
                    "symbol=%s | timeframe=%s | "
                    "requested_start=%s | requested_end=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    last_error,
                )
                return None

            original_count = len(rates)

            if original_count == 0:
                return rates

            timestamps = rates["time"]

            start_epoch = requested_start.timestamp()
            end_epoch = requested_end.timestamp()

            valid_mask = (
                (timestamps >= start_epoch)
                & (timestamps < end_epoch)
                & (timestamps > 0)
            )

            valid_count = int(valid_mask.sum())
            rejected_count = original_count - valid_count

            if rejected_count:
                try:
                    first_original = MarketDataBroker._describe_candle(rates[0])
                    last_original = MarketDataBroker._describe_candle(rates[-1])
                except (IndexError, TypeError, ValueError):
                    first_original = None
                    last_original = None

                logger.error(
                    "MT5 returned candles outside the requested "
                    "historical range; filtering invalid candles | "
                    "symbol=%s | timeframe=%s | "
                    "requested_start=%s | requested_end=%s | "
                    "received=%s | accepted=%s | rejected=%s | "
                    "original_first=%s | original_last=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    original_count,
                    valid_count,
                    rejected_count,
                    first_original,
                    last_original,
                    last_error,
                )

            filtered_rates = rates[valid_mask]

            if len(filtered_rates) == 0 and original_count > 0:
                logger.error(
                    "No MT5 candles remain inside the requested "
                    "historical range | "
                    "symbol=%s | timeframe=%s | "
                    "requested_start=%s | requested_end=%s | "
                    "original_count=%s | rejected_count=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    original_count,
                    rejected_count,
                    last_error,
                )

            return filtered_rates

        except (
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            logger.exception(
                "Could not validate MT5 candle timestamps; "
                "rejecting the response | "
                "symbol=%s | timeframe=%s | "
                "requested_start=%s | requested_end=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                requested_start.isoformat(),
                requested_end.isoformat(),
                last_error,
            )
            return None

    # =========================================================
    # CANDLE DIAGNOSTICS
    # =========================================================

    @staticmethod
    def _describe_candle(
        rate: Any,
    ) -> dict[str, Any]:
        """Extract diagnostic information from an MT5 NumPy candle."""
        try:
            timestamp = rate["time"]
        except (KeyError, IndexError, TypeError, ValueError):
            timestamp = None

        timestamp_utc = MarketDataBroker._timestamp_to_utc(
            timestamp,
        )

        description: dict[str, Any] = {
            "timestamp": (int(timestamp) if timestamp is not None else None),
            "timestamp_utc": (
                timestamp_utc.isoformat() if timestamp_utc is not None else None
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
            except (KeyError, IndexError, TypeError, ValueError):
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
        Log diagnostics for a historical range response.

        Includes returned candle count, first and last timestamps,
        returned timespan and sparse-range warnings.
        """
        try:
            rate_count = len(rates)

        except (TypeError, ValueError):
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

        first_candle = MarketDataBroker._describe_candle(rates[0])
        last_candle = MarketDataBroker._describe_candle(rates[-1])

        first_datetime = MarketDataBroker._timestamp_to_utc(
            first_candle.get("timestamp"),
        )
        last_datetime = MarketDataBroker._timestamp_to_utc(
            last_candle.get("timestamp"),
        )

        returned_span_seconds: float | None = None

        if first_datetime is not None and last_datetime is not None:
            returned_span_seconds = (last_datetime - first_datetime).total_seconds()

        requested_span_seconds = (requested_end - requested_start).total_seconds()

        logger.info(
            "MT5 historical range diagnostics | "
            "symbol=%s | timeframe=%s | "
            "requested_start=%s | requested_end=%s | "
            "requested_span_seconds=%s | returned_count=%s | "
            "first_timestamp=%s | first_timestamp_utc=%s | "
            "last_timestamp=%s | last_timestamp_utc=%s | "
            "returned_span_seconds=%s | last_error=%s",
            symbol,
            timeframe,
            requested_start.isoformat(),
            requested_end.isoformat(),
            requested_span_seconds,
            rate_count,
            first_candle.get("timestamp"),
            first_candle.get("timestamp_utc"),
            last_candle.get("timestamp"),
            last_candle.get("timestamp_utc"),
            returned_span_seconds,
            last_error,
        )

        logger.info(
            "MT5 first historical candle | " "symbol=%s | timeframe=%s | candle=%s",
            symbol,
            timeframe,
            first_candle,
        )

        logger.info(
            "MT5 last historical candle | " "symbol=%s | timeframe=%s | candle=%s",
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
                "returned_span_seconds=%s | returned_count=%s | "
                "first=%s | last=%s | last_error=%s",
                symbol,
                timeframe,
                requested_span_seconds,
                returned_span_seconds,
                rate_count,
                first_candle.get("timestamp_utc"),
                last_candle.get("timestamp_utc"),
                last_error,
            )

    # =========================================================
    # TICK VALIDATION
    # =========================================================

    @staticmethod
    def _validate_tick(
        symbol: str,
        tick: Any,
    ) -> bool:
        """
        Reject invalid ticks before they enter the AQE data pipeline.

        This method is called from get_tick(), while the shared lock
        remains held.
        """
        if tick is None:
            logger.warning(
                "MT5 returned no tick | symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return False

        try:
            data = tick._asdict()

        except (AttributeError, TypeError):
            logger.error(
                "Invalid MT5 tick object | symbol=%s | tick=%r",
                symbol,
                tick,
            )
            return False

        try:
            timestamp_value = int(data.get("time") or 0)
            bid_value = float(data.get("bid") or 0.0)
            ask_value = float(data.get("ask") or 0.0)

        except (TypeError, ValueError, OverflowError):
            logger.error(
                "Invalid MT5 tick values | " "symbol=%s | tick=%r | last_error=%s",
                symbol,
                data,
                MarketDataBroker._last_error(),
            )
            return False

        if timestamp_value <= 0:
            logger.warning(
                "Rejected MT5 tick: invalid timestamp | "
                "symbol=%s | timestamp=%r | tick=%r | "
                "last_error=%s",
                symbol,
                data.get("time"),
                data,
                MarketDataBroker._last_error(),
            )
            return False

        if not math.isfinite(bid_value) or bid_value <= 0:
            logger.warning(
                "Rejected MT5 tick: invalid bid | "
                "symbol=%s | bid=%r | tick=%r | last_error=%s",
                symbol,
                data.get("bid"),
                data,
                MarketDataBroker._last_error(),
            )
            return False

        if not math.isfinite(ask_value) or ask_value <= 0:
            logger.warning(
                "Rejected MT5 tick: invalid ask | "
                "symbol=%s | ask=%r | tick=%r | last_error=%s",
                symbol,
                data.get("ask"),
                data,
                MarketDataBroker._last_error(),
            )
            return False

        if ask_value < bid_value:
            logger.warning(
                "Rejected MT5 tick: ask is below bid | "
                "symbol=%s | bid=%s | ask=%s | tick=%r | "
                "last_error=%s",
                symbol,
                bid_value,
                ask_value,
                data,
                MarketDataBroker._last_error(),
            )
            return False

        return True

    # =========================================================
    # TICK RETRIEVAL
    # =========================================================

    @staticmethod
    @mt5_synchronized
    def get_tick(symbol: str):
        """
        Retrieve the latest valid tick.

        The shared MT5 lock covers terminal checking, symbol selection,
        tick retrieval and tick validation.
        """
        symbol = symbol.strip()

        if not symbol:
            logger.warning("Cannot retrieve tick: empty symbol.")
            return None

        if not MarketDataBroker._terminal_ready():
            logger.error(
                "Cannot retrieve tick: MT5 terminal unavailable | "
                "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return None

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        try:
            tick = mt5.symbol_info_tick(symbol)

        except Exception:
            logger.exception(
                "MT5 tick retrieval raised an exception | " "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return None

        if not MarketDataBroker._validate_tick(symbol, tick):
            return None

        return tick

    # =========================================================
    # CANDLE RETRIEVAL
    # =========================================================

    @staticmethod
    @mt5_synchronized
    def get_candles(
        symbol: str,
        timeframe: int,
        count: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        """
        Retrieve historical OHLCV candles from MT5.

        Range mode:
            If start or end is supplied, use copy_rates_range().
            Returned candles are validated against the requested range.

        Latest-N mode:
            If neither start nor end is supplied, use
            copy_rates_from_pos().

        Returns:
            Non-empty NumPy structured array for valid candles.
            Empty NumPy structured array for a valid empty result.
            None for an unavailable terminal, invalid request or
            failed retrieval.

        The shared lock covers the entire operation, including symbol
        selection, date normalization, retrieval and diagnostics.
        """
        if not isinstance(symbol, str):
            logger.warning(
                "Cannot retrieve candles: symbol must be a string | " "symbol=%r",
                symbol,
            )
            return None

        symbol = symbol.strip()

        if not symbol:
            logger.warning("Cannot retrieve candles: empty symbol.")
            return None

        if not isinstance(timeframe, int) or isinstance(timeframe, bool):
            logger.warning(
                "Invalid MT5 timeframe | symbol=%s | timeframe=%r",
                symbol,
                timeframe,
            )
            return None

        # ---------------------------------------------------------
        # Verify terminal availability.
        # ---------------------------------------------------------

        if not MarketDataBroker._terminal_ready():
            logger.error(
                "MT5 terminal information unavailable or disconnected "
                "while retrieving candles | symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return None

        # ---------------------------------------------------------
        # Ensure the symbol is available.
        # ---------------------------------------------------------

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        try:
            symbol_info = mt5.symbol_info(symbol)

        except Exception:
            logger.exception(
                "MT5 symbol verification raised an exception | "
                "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return None

        if symbol_info is None:
            logger.error(
                "MT5 symbol information unavailable | " "symbol=%s | last_error=%s",
                symbol,
                MarketDataBroker._last_error(),
            )
            return None

        # ---------------------------------------------------------
        # Normalize dates and validate the requested interval.
        # ---------------------------------------------------------

        start = MarketDataBroker._normalize_utc(start)
        end = MarketDataBroker._normalize_utc(end)

        if start is not None and end is not None and start >= end:
            logger.warning(
                "Invalid or empty candle range | " "symbol=%s | start=%s | end=%s",
                symbol,
                start.isoformat(),
                end.isoformat(),
            )
            return None

        # =========================================================
        # RANGE-BASED RETRIEVAL
        # =========================================================

        if start is not None or end is not None:
            if start is None:
                start = end

            if end is None:
                end = datetime.now(timezone.utc)

            requested_start = start
            requested_end = end

            if requested_start is None or requested_end is None:
                logger.error(
                    "Could not establish historical candle range | "
                    "symbol=%s | start=%s | end=%s",
                    symbol,
                    requested_start,
                    requested_end,
                )
                return None

            if requested_start >= requested_end:
                logger.warning(
                    "Invalid or empty candle range | " "symbol=%s | start=%s | end=%s",
                    symbol,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                )
                return None

            if count is not None:
                if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                    logger.warning(
                        "Invalid candle count | symbol=%s | count=%r",
                        symbol,
                        count,
                    )
                    return None

            logger.info(
                "Requesting MT5 historical candles | "
                "symbol=%s | timeframe=%s | start=%s | end=%s",
                symbol,
                timeframe,
                requested_start.isoformat(),
                requested_end.isoformat(),
            )

            try:
                rates = mt5.copy_rates_range(
                    symbol,
                    timeframe,
                    requested_start,
                    requested_end,
                )

            except Exception:
                logger.exception(
                    "MT5 copy_rates_range raised an exception | "
                    "symbol=%s | timeframe=%s | start=%s | end=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    MarketDataBroker._last_error(),
                )
                return None

            # Capture the error immediately after the original MT5 call.
            last_error = MarketDataBroker._last_error()

            # -----------------------------------------------------
            # TEMPORARY DIAGNOSTIC ONLY
            #
            # Compare copy_rates_range() with copy_rates_from() for
            # the known BTCUSD.s March 3, 2023 failure.
            #
            # The alternative result is logged only. It is never
            # returned to AQE and never bypasses range validation.
            # Remove this block after collecting the diagnostic logs.
            # -----------------------------------------------------

            if (
                symbol == "BTCUSD.s"
                and requested_start.date() == datetime(2023, 3, 3).date()
            ):
                diagnostic_count = 500

                try:
                    alternative_rates = mt5.copy_rates_from(
                        symbol,
                        timeframe,
                        requested_end,
                        diagnostic_count,
                    )

                    alternative_error = MarketDataBroker._last_error()

                    if alternative_rates is None:
                        logger.warning(
                            "MT5 alternative historical diagnostic "
                            "returned None | "
                            "symbol=%s | timeframe=%s | "
                            "requested_start=%s | requested_end=%s | "
                            "requested_count=%s | error=%s",
                            symbol,
                            timeframe,
                            requested_start.isoformat(),
                            requested_end.isoformat(),
                            diagnostic_count,
                            alternative_error,
                        )

                    else:
                        alternative_count = len(alternative_rates)

                        first_alternative = None
                        last_alternative = None
                        in_range_count = 0

                        if alternative_count:
                            first_alternative = MarketDataBroker._describe_candle(
                                alternative_rates[0]
                            )
                            last_alternative = MarketDataBroker._describe_candle(
                                alternative_rates[-1]
                            )

                            dtype_names = getattr(
                                getattr(alternative_rates, "dtype", None),
                                "names",
                                None,
                            )

                            if dtype_names and "time" in dtype_names:
                                alternative_timestamps = alternative_rates["time"]

                                start_epoch = requested_start.timestamp()
                                end_epoch = requested_end.timestamp()

                                alternative_mask = (
                                    (alternative_timestamps >= start_epoch)
                                    & (alternative_timestamps < end_epoch)
                                    & (alternative_timestamps > 0)
                                )

                                in_range_count = int(alternative_mask.sum())

                        logger.warning(
                            "MT5 alternative historical diagnostic | "
                            "symbol=%s | timeframe=%s | "
                            "requested_start=%s | requested_end=%s | "
                            "requested_count=%s | returned_count=%s | "
                            "in_range_count=%s | first=%s | last=%s | "
                            "error=%s",
                            symbol,
                            timeframe,
                            requested_start.isoformat(),
                            requested_end.isoformat(),
                            diagnostic_count,
                            alternative_count,
                            in_range_count,
                            first_alternative,
                            last_alternative,
                            alternative_error,
                        )

                except Exception:
                    logger.exception(
                        "MT5 alternative historical diagnostic failed | "
                        "symbol=%s | timeframe=%s | "
                        "requested_start=%s | requested_end=%s",
                        symbol,
                        timeframe,
                        requested_start.isoformat(),
                        requested_end.isoformat(),
                    )

            # -----------------------------------------------------
            # Continue with the original range-retrieval behavior.
            # -----------------------------------------------------

            if rates is None:
                if MarketDataBroker._is_connection_error(last_error):
                    logger.error(
                        "Historical retrieval failed because of an "
                        "MT5 IPC/connection error | "
                        "symbol=%s | timeframe=%s | "
                        "start=%s | end=%s | last_error=%s",
                        symbol,
                        timeframe,
                        requested_start.isoformat(),
                        requested_end.isoformat(),
                        last_error,
                    )
                else:
                    logger.error(
                        "MT5 copy_rates_range returned None | "
                        "symbol=%s | timeframe=%s | "
                        "start=%s | end=%s | last_error=%s",
                        symbol,
                        timeframe,
                        requested_start.isoformat(),
                        requested_end.isoformat(),
                        last_error,
                    )

                return None

            try:
                original_count = len(rates)

            except (TypeError, ValueError):
                logger.error(
                    "Unexpected MT5 candle result | "
                    "symbol=%s | timeframe=%s | result=%r | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    rates,
                    last_error,
                )
                return None

            if original_count == 0:
                MarketDataBroker._log_range_result(
                    symbol=symbol,
                    timeframe=timeframe,
                    requested_start=requested_start,
                    requested_end=requested_end,
                    rates=rates,
                    last_error=last_error,
                )
                return rates

            # -----------------------------------------------------
            # CRITICAL FIX:
            # Validate actual timestamps before returning data or
            # applying the optional count limit.
            # -----------------------------------------------------

            rates = MarketDataBroker._filter_rates_to_requested_range(
                symbol=symbol,
                timeframe=timeframe,
                requested_start=requested_start,
                requested_end=requested_end,
                rates=rates,
                last_error=last_error,
            )

            if rates is None:
                return None

            rate_count = len(rates)

            if rate_count == 0:
                logger.warning(
                    "MT5 historical response contained no valid "
                    "candles for the requested range | "
                    "symbol=%s | timeframe=%s | "
                    "start=%s | end=%s | "
                    "original_count=%s | last_error=%s",
                    symbol,
                    timeframe,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    original_count,
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

            MarketDataBroker._log_range_result(
                symbol=symbol,
                timeframe=timeframe,
                requested_start=requested_start,
                requested_end=requested_end,
                rates=rates,
                last_error=last_error,
            )

            # -----------------------------------------------------
            # Optional range-result limit.
            # -----------------------------------------------------

            if count is not None and rate_count > count:
                logger.debug(
                    "Limiting validated MT5 historical result | "
                    "symbol=%s | timeframe=%s | "
                    "original_count=%s | requested_count=%s",
                    symbol,
                    timeframe,
                    rate_count,
                    count,
                )

                rates = rates[-count:]

            logger.info(
                "MT5 historical candles retrieved and validated | "
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

        # =========================================================
        # LATEST-N RETRIEVAL
        # =========================================================

        if count is None:
            count = 100

        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            logger.warning(
                "Invalid candle count | symbol=%s | count=%r",
                symbol,
                count,
            )
            return None

        logger.info(
            "Requesting latest MT5 candles | " "symbol=%s | timeframe=%s | count=%s",
            symbol,
            timeframe,
            count,
        )

        try:
            rates = mt5.copy_rates_from_pos(
                symbol,
                timeframe,
                0,
                count,
            )

        except Exception:
            logger.exception(
                "MT5 copy_rates_from_pos raised an exception | "
                "symbol=%s | timeframe=%s | count=%s | "
                "last_error=%s",
                symbol,
                timeframe,
                count,
                MarketDataBroker._last_error(),
            )
            return None

        last_error = MarketDataBroker._last_error()

        if rates is None:
            if MarketDataBroker._is_connection_error(last_error):
                logger.error(
                    "Latest candle retrieval failed due to an MT5 "
                    "IPC/connection error | "
                    "symbol=%s | timeframe=%s | count=%s | "
                    "last_error=%s",
                    symbol,
                    timeframe,
                    count,
                    last_error,
                )
            else:
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

        except (TypeError, ValueError):
            logger.error(
                "Unexpected MT5 candle result | "
                "symbol=%s | timeframe=%s | result=%r | "
                "last_error=%s",
                symbol,
                timeframe,
                rates,
                last_error,
            )
            return None

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

        first_candle = MarketDataBroker._describe_candle(rates[0])
        last_candle = MarketDataBroker._describe_candle(rates[-1])

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
