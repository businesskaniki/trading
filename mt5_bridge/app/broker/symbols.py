import MetaTrader5 as mt5

from app.core.logging import logger


class SymbolBroker:

    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

    @staticmethod
    def get_symbols():
        return mt5.symbols_get()

    @staticmethod
    def get_symbol(symbol: str):
        return mt5.symbol_info(symbol)

    @staticmethod
    def tick(symbol: str):

        info = mt5.symbol_info(symbol)

        if info is None:
            logger.warning("Symbol not found: %s error=%s", symbol, mt5.last_error())
            return None

        if not info.visible:

            selected = mt5.symbol_select(
                symbol,
                True,
            )

            if not selected:
                logger.warning("Unable to select symbol: %s error=%s", symbol, mt5.last_error())
                return None

        tick = mt5.symbol_info_tick(symbol)

        return tick

    @staticmethod
    def get_candles(
        symbol: str,
        timeframe: str,
        count: int,
    ):

        mt5_timeframe = SymbolBroker.TIMEFRAME_MAP.get(timeframe)

        if mt5_timeframe is None:
            logger.warning("Unknown timeframe: %s", timeframe)
            return None

        info = mt5.symbol_info(symbol)

        if info is None:
            logger.warning("Symbol not found: %s error=%s", symbol, mt5.last_error())
            return None

        if not info.visible:

            selected = mt5.symbol_select(
                symbol,
                True,
            )

            if not selected:
                logger.warning("Unable to select symbol: %s error=%s", symbol, mt5.last_error())
                return None

        rates = mt5.copy_rates_from_pos(
            symbol,
            mt5_timeframe,
            0,
            count,
        )

        if rates is None:
            return None

        return rates
