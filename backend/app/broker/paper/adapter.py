from datetime import datetime, timezone

from app.broker.base import BrokerAdapter


class PaperBroker(BrokerAdapter):

    def __init__(self):
        self.connected = False
        self.balance = 100000.0
        self.orders = []
        self.positions = []
        self.next_ticket = 1

    async def connect(self, credentials=None):
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False

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
        return []

    async def get_symbol(self, symbol):
        return {"symbol": symbol}

    async def get_tick(self, symbol):
        return {"symbol": symbol, "bid": 0.0, "ask": 0.0}

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