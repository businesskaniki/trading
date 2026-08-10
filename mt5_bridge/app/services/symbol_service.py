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