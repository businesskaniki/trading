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