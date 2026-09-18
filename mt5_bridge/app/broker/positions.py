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

        if result is None:

            raise Exception(
                f"Position close failed. "
                f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:

            raise Exception(
                f"Position close failed. "
                f"retcode={result.retcode}, "
                f"comment={result.comment}"
            )

        return {
            "retcode": result.retcode,
            "comment": result.comment,
            "order": result.order,
            "deal": result.deal,
        }


    @staticmethod
    def modify(
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ):

        positions = mt5.positions_get(
            ticket=ticket
        )

        if not positions:
            return None

        position = positions[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": sl if sl is not None else position.sl,
            "tp": tp if tp is not None else position.tp,
        }

        result = mt5.order_send(request)

        if result is None:

            raise Exception(
                f"Position modification failed. "
                f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:

            raise Exception(
                f"Position modification failed. "
                f"MT5 retcode: {result.retcode}, "
                f"comment: {result.comment}"
            )

        return result._asdict()

    @staticmethod
    def modify(
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ):

        positions = mt5.positions_get(ticket=ticket)

        if not positions:
            return None

        position = positions[0]

        # Keep existing values when one value isn't supplied.
        new_sl = position.sl if sl is None else sl
        new_tp = position.tp if tp is None else tp

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": new_sl,
            "tp": new_tp,
        }

        result = mt5.order_send(request)

        if result is None:
            raise Exception(
                f"Position modification failed. "
                f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise Exception(
                f"Position modification failed. "
                f"MT5 retcode: {result.retcode}, "
                f"comment: {result.comment}"
            )

        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": new_tp,
            "retcode": result.retcode,
            "comment": result.comment,
        }