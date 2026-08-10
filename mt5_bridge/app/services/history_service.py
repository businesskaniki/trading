from datetime import datetime

from app.broker.history import HistoryBroker


class HistoryService:

    def __init__(self):
        self.broker = HistoryBroker()

    def orders(
        self,
        date_from: datetime,
        date_to: datetime,
    ):

        orders = self.broker.orders(
            date_from,
            date_to,
        )

        if orders is None:
            return []

        return [
            order._asdict()
            for order in orders
        ]

    def deals(
        self,
        date_from: datetime,
        date_to: datetime,
    ):

        deals = self.broker.deals(
            date_from,
            date_to,
        )

        if deals is None:
            return []

        return [
            deal._asdict()
            for deal in deals
        ]
    