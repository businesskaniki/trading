from app.broker.orders import OrderBroker


class OrderService:

    def __init__(self):
        self.broker = OrderBroker()

    def send_order(
        self,
        request: dict,
    ):

        mt5_request = {
            "action": 1,  # TRADE_ACTION_DEAL
            "symbol": request["symbol"],
            "volume": request["volume"],
            "type": request["order_type"],
            "price": request["price"],
            "deviation": request.get("deviation", 20),
            "magic": request.get("magic", 0),
            "comment": str(request.get("comment", "AQE"))[:31],
        }

        # Only add SL when an actual value was supplied
        if request.get("sl") is not None:
            mt5_request["sl"] = request["sl"]

        # Only add TP when an actual value was supplied
        if request.get("tp") is not None:
            mt5_request["tp"] = request["tp"]

        result = self.broker.send(mt5_request)

        if result is None:
            raise Exception(
                "Order submission failed. "
                f"MT5 error: {self.broker.last_error()}"
            )

        if result.retcode != 10009:
            raise Exception(
                f"Order submission failed. "
                f"MT5 error: {result.retcode}, "
                f"{result.comment}"
            )

        return {
            "ticket": result.order or result.deal,
            "symbol": result.request.symbol,
            "volume": result.volume,
            "price_open": result.price,
            "sl": result.request.sl,
            "tp": result.request.tp,
            "order_type": result.request.type,
            "state": result.retcode,
            "comment": result.comment,
        }

    def check_order(
        self,
        request: dict,
    ):

        result = self.broker.check(request)

        if result is None:
            return None

        return result._asdict()

    def list_orders(self):

        orders = self.broker.orders()

        if orders is None:
            return []

        return [
            order._asdict()
            for order in orders
        ]

    def get_order(
        self,
        ticket: int,
    ):

        orders = self.broker.order(ticket)

        if not orders:
            return None

        return orders[0]._asdict()


    def create_pending_order(
        self,
        symbol: str,
        volume: float,
        order_type: int,
        price: float,
        sl=None,
        tp=None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "",
    ):

        result = self.broker.pending(
            symbol=symbol,
            volume=volume,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            deviation=deviation,
            magic=magic,
            comment=comment,
        )

        return {
            "ticket": result.order,
            "symbol": symbol,
            "volume": volume,
            "price_open": price,
            "sl": sl or 0.0,
            "tp": tp or 0.0,
            "order_type": order_type,
            "state": result.retcode,
            "comment": result.comment,
        }