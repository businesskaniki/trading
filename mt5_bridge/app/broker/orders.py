import MetaTrader5 as mt5


class OrderBroker:

    @staticmethod
    def send(request: dict):

        return mt5.order_send(request)

    @staticmethod
    def check(request: dict):

        return mt5.order_check(request)

    @staticmethod
    def orders():

        return mt5.orders_get()

    @staticmethod
    def order(ticket: int):

        return mt5.orders_get(ticket=ticket)

    @staticmethod
    def last_error():

        return mt5.last_error()

    @staticmethod
    def pending(
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

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
        }

        if sl is not None:
            request["sl"] = sl

        if tp is not None:
            request["tp"] = tp

        result = mt5.order_send(request)

        if result is None:
            raise Exception(
                f"Pending order submission failed. "
                f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise Exception(
                f"Pending order submission failed. "
                f"MT5 retcode: {result.retcode}, "
                f"comment: {result.comment}"
            )

        return result