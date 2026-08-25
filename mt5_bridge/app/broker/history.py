import MetaTrader5 as mt5
from datetime import datetime


class HistoryBroker:

    # ==========================================================
    # ORDER HISTORY
    # ==========================================================

    @staticmethod
    def orders(
        start: datetime,
        end: datetime,
    ):
        return mt5.history_orders_get(
            start,
            end,
        )

    # ==========================================================
    # DEAL HISTORY
    # ==========================================================

    @staticmethod
    def deals(
        start: datetime,
        end: datetime,
    ):
        return mt5.history_deals_get(
            start,
            end,
        )

    # ==========================================================
    # DEALS BY POSITION
    # ==========================================================

    @staticmethod
    def deals_by_position(
        position_id: int,
    ):
        """
        Return all historical deals belonging to a position.
        """

        return mt5.history_deals_get(
            position=position_id,
        )