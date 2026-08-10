from app.broker.base import BrokerInterface


class PaperBroker(BrokerInterface):

    async def connect(self):
        return True

    async def disconnect(self):
        return None

    async def account_info(self):
        return {
            "broker": "Paper Trading",
            "balance": 100000,
            "equity": 100000,
            "currency": "USD",
        }

    async def symbols(self):
        return []

    async def place_order(self, order):
        return {
            "status": "FILLED",
            "ticket": "PAPER-000001",
        }

    async def modify_order(self, order_id, **kwargs):
        return True

    async def cancel_order(self, order_id):
        return True

    async def open_positions(self):
        return []

    async def close_position(self, position_id):
        return True

    async def order_history(self):
        return []

    async def trade_history(self):
        return []