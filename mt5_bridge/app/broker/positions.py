from __future__ import annotations

import MetaTrader5 as mt5


class PositionBroker:
    """
    Low-level MetaTrader 5 position operations.

    This class talks directly to the MT5 Python API.
    Business logic and response normalization belong to the
    service layer.
    """

    @staticmethod
    def positions():
        """
        Return all currently open MT5 positions.
        """

        return mt5.positions_get()

    @staticmethod
    def position(ticket: int):
        """
        Return a single MT5 position by broker position ticket.
        """

        return mt5.positions_get(ticket=ticket)

    @staticmethod
    def by_symbol(symbol: str):
        """
        Return all open MT5 positions for a symbol.
        """

        return mt5.positions_get(symbol=symbol)

    @staticmethod
    def close(ticket: int):
        """
        Close an MT5 position.

        The service layer is responsible for determining the
        opposite order type, volume, and price.
        """

        positions = mt5.positions_get(ticket=ticket)

        if not positions:
            return None

        position = positions[0]

        tick = mt5.symbol_info_tick(position.symbol)

        if tick is None:
            raise RuntimeError(
                f"Unable to retrieve tick for " f"position symbol '{position.symbol}'."
            )

        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        elif position.type == mt5.POSITION_TYPE_SELL:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            raise RuntimeError(f"Unsupported MT5 position type: {position.type}")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": 0,
            "comment": "AQE position close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result is None:
            raise RuntimeError(
                "Position close failed. " f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode not in (
            mt5.TRADE_RETCODE_DONE,
            mt5.TRADE_RETCODE_DONE_PARTIAL,
        ):
            raise RuntimeError(
                "Position close failed. "
                f"retcode={result.retcode}, "
                f"comment={result.comment}"
            )

        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "retcode": result.retcode,
            "comment": result.comment,
            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),
            "position": getattr(result, "position", None),
        }

    @staticmethod
    def modify(
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """
        Modify stop-loss and/or take-profit for an open position.
        """

        positions = mt5.positions_get(ticket=ticket)

        if not positions:
            return None

        position = positions[0]

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
            raise RuntimeError(
                "Position modification failed. " f"MT5 error: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                "Position modification failed. "
                f"MT5 retcode={result.retcode}, "
                f"comment={result.comment}"
            )

        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": new_tp,
            "retcode": result.retcode,
            "comment": result.comment,
        }
