from datetime import datetime

import MetaTrader5 as mt5


class HistoryBroker:

    @staticmethod
    def deals(
        date_from: datetime,
        date_to: datetime,
    ):

        return mt5.history_deals_get(
            date_from,
            date_to,
        )

    @staticmethod
    def orders(
        date_from: datetime,
        date_to: datetime,
    ):

        return mt5.history_orders_get(
            date_from,
            date_to,
        )