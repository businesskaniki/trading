import MetaTrader5 as mt5


class SymbolBroker:

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
            print(
                f"DEBUG: symbol not found: {symbol}"
            )
            print(
                f"DEBUG: MT5 error: {mt5.last_error()}"
            )
            return None

        print(
            f"DEBUG: visible = {info.visible}"
        )

        if not info.visible:

            print(
                f"DEBUG: selecting symbol {symbol}"
            )

            selected = mt5.symbol_select(
                symbol,
                True,
            )

            print(
                f"DEBUG: symbol_select = {selected}"
            )

            if not selected:
                print(
                    f"DEBUG: MT5 error: {mt5.last_error()}"
                )
                return None

        tick = mt5.symbol_info_tick(symbol)

        print(
            f"DEBUG: tick = {tick}"
        )

        print(
            f"DEBUG: MT5 error = {mt5.last_error()}"
        )

        return tick