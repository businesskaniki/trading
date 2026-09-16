import MetaTrader5 as mt5

from datetime import datetime

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
                "Symbol not found in MT5: %s",
                symbol,
            )
            return False

        if not info.visible:
            selected = mt5.symbol_select(
                symbol,
                True,
            )

            if not selected:
                logger.error(
                    "Failed to select symbol %s: %s",
                    symbol,
                    mt5.last_error(),
                )
                return False

        return True

    @staticmethod
    def _validate_tick(symbol: str, tick) -> bool:
        """
        Validate a raw MT5 tick before it is allowed into AQE.

        MT5 can return a tick structure containing zero/default
        values when usable market data is not actually available.

        Such ticks must never be published to Redis.
        """

        if tick is None:
            logger.warning(
                "MT5 returned no tick for %s: %s",
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
                "Rejected MT5 tick for %s: invalid bid=%r " "raw_tick=%r last_error=%s",
                symbol,
                bid,
                data,
                mt5.last_error(),
            )
            return False

        if ask_value <= 0:
            logger.warning(
                "Rejected MT5 tick for %s: invalid ask=%r " "raw_tick=%r last_error=%s",
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
        Retrieve historical OHLCV candles from MT5.

        When `start` and/or `end` are supplied, MT5 range-based
        retrieval is used through `copy_rates_range()`.

        When no range is supplied, the method falls back to the
        latest-N candle behavior using `copy_rates_from_pos()`.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve candles: empty symbol.",
            )
            return None

        if not MarketDataBroker._ensure_symbol_selected(symbol):
            return None

        if start is not None and end is not None:
            if start > end:
                logger.warning(
                    "Invalid candle range for %s: start=%s is later than end=%s",
                    symbol,
                    start,
                    end,
                )
                return None

        if start is not None or end is not None:
            if start is None:
                start = end

            if end is None:
                end = datetime.now(start.tzinfo)

            rates = mt5.copy_rates_range(
                symbol,
                timeframe,
                start,
                end,
            )

            if rates is None:
                logger.error(
                    "Failed to retrieve candle range for %s: %s",
                    symbol,
                    mt5.last_error(),
                )
                return None

            if count is not None and count > 0:
                rates = rates[-count:]

            return rates

        if count is None:
            count = 100

        if count < 1:
            logger.warning(
                "Invalid candle count for %s: %s",
                symbol,
                count,
            )
            return None

        rates = mt5.copy_rates_from_pos(
            symbol,
            timeframe,
            0,
            count,
        )

        if rates is None:
            logger.error(
                "Failed to retrieve candles for %s: %s",
                symbol,
                mt5.last_error(),
            )
            return None

        return rates
