from app.broker.symbols import SymbolBroker


class SymbolService:

    def __init__(self):
        self.broker = SymbolBroker()

    def list_symbols(self):

        symbols = self.broker.get_symbols()

        if symbols is None:
            return []

        return [
            symbol._asdict()
            for symbol in symbols
        ]

    def get_symbol(
        self,
        symbol: str,
    ):

        data = self.broker.get_symbol(symbol)

        if data is None:
            return None

        return data._asdict()

    def get_tick(
        self,
        symbol: str,
    ):

        tick = self.broker.tick(symbol)

        if tick is None:
            return None

        data = tick._asdict()

        return {
            "symbol": symbol,
            **data,
        }

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ):

        rates = self.broker.get_candles(
            symbol,
            timeframe,
            count,
        )

        if rates is None:
            return None

        # rates is a numpy structured array (from mt5.copy_rates_from_pos) -
        # fields are accessed by name, not ._asdict() like the namedtuples
        # tick()/get_symbol() return.
        candles = []

        for rate in rates:
            candles.append(
                {
                    "time": int(rate["time"]),
                    "open": float(rate["open"]),
                    "high": float(rate["high"]),
                    "low": float(rate["low"]),
                    "close": float(rate["close"]),
                    "volume": int(rate["tick_volume"]),
                    "spread": int(rate["spread"]),
                }
            )

        return candles