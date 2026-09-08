from datetime import datetime, timezone

from app.broker.base import BrokerAdapter


class PaperBroker(BrokerAdapter):
    """
    Simulated broker - orders and positions are tracked locally and
    never sent to a real broker.

    Price data (get_tick / get_candles) is a separate concern from
    order simulation: a paper account should see the same real
    prices a live account would, it just shouldn't be able to act on
    them for real. Pass a market_data_source (e.g. a connected
    MT5Adapter, used only for reads) to proxy real prices through.
    Without one, this falls back to the old dummy zero-price
    behavior rather than breaking.
    """

    def __init__(self, market_data_source: BrokerAdapter | None = None):
        self.connected = False
        self.balance = 100000.0
        self.orders = []
        self.positions = []
        self.next_ticket = 1
        self.market_data_source = market_data_source

    async def connect(self, credentials=None):
        self.connected = True

        if self.market_data_source is not None:
            await self.market_data_source.connect(credentials)

        return True

    async def disconnect(self):
        self.connected = False

        if self.market_data_source is not None:
            await self.market_data_source.disconnect()

    async def connection_status(self):
        return {"connected": self.connected, "broker": "paper"}

    async def get_account(self):
        return {
            "broker": "Paper Trading",
            "balance": self.balance,
            "equity": self.balance,
            "currency": "USD",
        }

    async def get_symbols(self):
        if self.market_data_source is not None:
            return await self.market_data_source.get_symbols()
        return []

    async def get_symbol(self, symbol):
        if self.market_data_source is not None:
            return await self.market_data_source.get_symbol(symbol)
        return {"symbol": symbol}

    async def get_tick(self, symbol):
        if self.market_data_source is not None:
            return await self.market_data_source.get_tick(symbol)
        return {"symbol": symbol, "bid": 0.0, "ask": 0.0}

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ):
        """
        Without a market_data_source, there is no real price history
        to draw from - returns an empty list rather than fabricating
        data, matching get_tick()'s existing "not really implemented"
        honesty. A strategy will simply never see enough candles to
        signal, which is the correct (if unhelpful) behavior until a
        market_data_source is wired up.
        """

        if self.market_data_source is not None:
            return await self.market_data_source.get_candles(
                symbol,
                timeframe=timeframe,
                count=count,
            )

        return []

    async def place_order(self, order):
        ticket = f"PAPER-{self.next_ticket:06d}"
        self.next_ticket += 1
        record = {
            "ticket": ticket,
            "status": "FILLED",
            "order": order.model_dump() if hasattr(order, "model_dump") else order,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.orders.append(record)
        return record

    async def create_pending_order(self, order):
        return await self.place_order(order)

    async def get_orders(self):
        return self.orders

    async def get_positions(self):
        return self.positions

    async def get_position(self, position_id):
        return next(
            (position for position in self.positions if position["id"] == position_id),
            None,
        )

    async def modify_position(self, position_id, sl=None, tp=None):
        position = await self.get_position(position_id)
        if position is None:
            return None
        if sl is not None:
            position["stop_loss"] = sl
        if tp is not None:
            position["take_profit"] = tp
        return position

    async def close_position(self, position_id):
        position = await self.get_position(position_id)
        if position is None:
            return None
        self.positions.remove(position)
        return {"status": "CLOSED", "position_id": position_id}

    async def get_order_history(self, start, end):
        return self.orders

    async def get_deal_history(self, start, end):
        return []