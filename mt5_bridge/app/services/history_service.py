from datetime import datetime

from app.broker.history import HistoryBroker


class HistoryService:

    def __init__(self):
        self.broker = HistoryBroker()

    # ==========================================================
    # ORDER HISTORY
    # ==========================================================

    def history_orders(
        self,
        start: datetime,
        end: datetime,
    ):

        orders = self.broker.orders(
            start,
            end,
        )

        if orders is None:
            return []

        return [
            {
                "ticket": order.ticket,
                "symbol": order.symbol,
                "volume": order.volume_initial,
                "price_open": order.price_open,
                "price_current": order.price_current,
                "sl": order.sl,
                "tp": order.tp,
                "state": order.state,
                "comment": order.comment,
                "time_setup": order.time_setup,
            }
            for order in orders
        ]

    # ==========================================================
    # DEAL HISTORY
    # ==========================================================

    def history_deals(
        self,
        start: datetime,
        end: datetime,
    ):

        deals = self.broker.deals(
            start,
            end,
        )

        if deals is None:
            return []

        return [
            {
                "ticket": deal.ticket,
                "order": deal.order,
                "position_id": getattr(
                    deal,
                    "position_id",
                    None,
                ),
                "symbol": deal.symbol,
                "volume": deal.volume,
                "price": deal.price,
                "profit": deal.profit,
                "commission": deal.commission,
                "swap": deal.swap,
                "comment": deal.comment,
                "time": deal.time,
                "entry": getattr(
                    deal,
                    "entry",
                    None,
                ),
            }
            for deal in deals
        ]

    def deals_by_position(
        self,
        position_id: int,
    ):

        deals = self.broker.deals_by_position(
            position_id
        )

        if deals is None:
            return []

        return [
            {
                "ticket": deal.ticket,
                "order": deal.order,
                "position_id": getattr(
                    deal,
                    "position_id",
                    None,
                ),
                "symbol": deal.symbol,
                "volume": deal.volume,
                "price": deal.price,
                "profit": deal.profit,
                "commission": deal.commission,
                "swap": deal.swap,
                "comment": deal.comment,
                "time": deal.time,
                "entry": getattr(
                    deal,
                    "entry",
                    None,
                ),
            }
            for deal in deals
        ]