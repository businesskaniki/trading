import MetaTrader5 as mt5


class PositionBroker:

    @staticmethod
    def positions():
        return mt5.positions_get()

    @staticmethod
    def position(ticket: int):
        return mt5.positions_get(ticket=ticket)

    @staticmethod
    def by_symbol(symbol: str):
        return mt5.positions_get(symbol=symbol)

    @staticmethod
    def close(ticket: int):

        positions = mt5.positions_get(ticket=ticket)

        if not positions:
            return None

        position = positions[0]

        tick = mt5.symbol_info_tick(position.symbol)

        if tick is None:
            raise Exception(
                f"Unable to retrieve tick for {position.symbol}"
            )

        # BUY positions are closed with a SELL order.
        # SELL positions are closed with a BUY order.
        if position.type == mt5.POSITION_TYPE_BUY:

            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        else:

            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": position.magic,
            "comment": "AQE CLOSE",
        }

        result = mt5.order_send(request)

        if result is None:
            raise Exception(
                f"Position close failed. MT5 error: "
                f"{mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise Exception(
                f"Position close failed. "
                f"MT5 retcode: {result.retcode}, "
                f"comment: {result.comment}"
            )

        return result._asdict()