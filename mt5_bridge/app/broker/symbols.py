import MetaTrader5 as mt5


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

        print(f"DEBUG: requesting tick for {symbol}")

        info = mt5.symbol_info(symbol)

        print(f"DEBUG: symbol info = {info}")

        if info is None:
            print(f"DEBUG: symbol not found: {symbol}")
            print(f"DEBUG: MT5 error: {mt5.last_error()}")
            return None

        print(f"DEBUG: visible = {info.visible}")

        if not info.visible:

            print(f"DEBUG: selecting symbol {symbol}")

            selected = mt5.symbol_select(
                symbol,
                True,
            )

            print(f"DEBUG: symbol_select = {selected}")

            if not selected:
                print(f"DEBUG: MT5 error: {mt5.last_error()}")
                return None

        tick = mt5.symbol_info_tick(symbol)

        print(f"DEBUG: tick = {tick}")

        print(f"DEBUG: MT5 error = {mt5.last_error()}")

        return tick

    @staticmethod
    def get_candles(
        symbol: str,
        timeframe: str,
        count: int,
    ):

        print(f"DEBUG: requesting " f"{count} {timeframe} candles for {symbol}")

        mt5_timeframe = SymbolBroker.TIMEFRAME_MAP.get(timeframe)

        if mt5_timeframe is None:
            print(f"DEBUG: unknown timeframe: {timeframe}")
            return None

        info = mt5.symbol_info(symbol)

        if info is None:
            print(f"DEBUG: symbol not found: {symbol}")
            print(f"DEBUG: MT5 error: {mt5.last_error()}")
            return None

        if not info.visible:

            selected = mt5.symbol_select(
                symbol,
                True,
            )

            if not selected:
                print(f"DEBUG: MT5 error: {mt5.last_error()}")
                return None

        rates = mt5.copy_rates_from_pos(
            symbol,
            mt5_timeframe,
            0,
            count,
        )

        print(f"DEBUG: rates = " f"{None if rates is None else len(rates)} bars")

        print(f"DEBUG: MT5 error = {mt5.last_error()}")

        if rates is None:
            return None

        return rates
