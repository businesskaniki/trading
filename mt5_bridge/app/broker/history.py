
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
        result = mt5.history_orders_get(start, end)

        if result is None:
            raise RuntimeError(
                "Failed to retrieve MT5 order history. "
                f"MT5 error: {mt5.last_error()}"
            )

        return result

    # ==========================================================
    # DEAL HISTORY
    # ==========================================================

    @staticmethod
    def deals(
        start: datetime,
        end: datetime,
    ):
        result = mt5.history_deals_get(start, end)

        if result is None:
            raise RuntimeError(
                "Failed to retrieve MT5 deal history. "
                f"MT5 error: {mt5.last_error()}"
            )

        return result

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

        result = mt5.history_deals_get(position=position_id)

        if result is None:
            raise RuntimeError(
                "Failed to retrieve MT5 deals for position "
                f"{position_id}. MT5 error: {mt5.last_error()}"
            )

        return result
