import MetaTrader5 as mt5

from app.core.logging import logger


class MarketDataBroker:
    """
    Low-level broker responsible for retrieving market data
    directly from MetaTrader 5.

    This class does not handle authentication or business logic.
    """

    @staticmethod
    def get_tick(symbol: str):
        """
        Retrieve the latest tick for a symbol.
        """

        info = mt5.symbol_info(symbol)

        if info is None:
            logger.warning(
                "Symbol not found: %s",
                symbol,
            )
            return None

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
                return None

        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            logger.error(
                "Failed to retrieve tick for %s: %s",
                symbol,
                mt5.last_error(),
            )
            return None

        return tick

    @staticmethod
    def get_candles(
        symbol: str,
        timeframe: int,
        count: int,
    ):
        """
        Retrieve historical OHLCV candles from MT5.

        `timeframe` should be an MT5 timeframe constant.
        """

        info = mt5.symbol_info(symbol)

        if info is None:
            logger.warning(
                "Symbol not found: %s",
                symbol,
            )
            return None

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
