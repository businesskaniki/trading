from __future__ import annotations

from typing import Any

import MetaTrader5 as mt5


class OrderBroker:
    """
    Low-level MetaTrader 5 order broker.

    This class is intentionally thin.

    Responsibilities:
        - Call the MT5 Python API.
        - Return raw MT5 results.
        - Expose basic MT5 order/account error information.
        - Expose symbol information required by the order service.

    Responsibilities that do NOT belong here:
        - AQE business rules.
        - Order lifecycle management.
        - Response normalization.
        - Broker-neutral mapping.
        - Deciding whether a retcode represents a successful
          application-level operation.

    Those responsibilities belong to OrderService.
    """

    @staticmethod
    def send(
        request: dict[str, Any],
    ) -> Any:
        """
        Submit an MT5 trade request.
        """

        return mt5.order_send(request)

    @staticmethod
    def check(
        request: dict[str, Any],
    ) -> Any:
        """
        Validate an MT5 trade request without submitting it.
        """

        return mt5.order_check(request)

    @staticmethod
    def orders() -> Any:
        """
        Retrieve all currently active/pending MT5 orders.
        """

        return mt5.orders_get()

    @staticmethod
    def order(
        ticket: int,
    ) -> Any:
        """
        Retrieve an active/pending MT5 order by broker order ticket.
        """

        return mt5.orders_get(ticket=ticket)

    @staticmethod
    def symbol_info(
        symbol: str,
    ) -> Any:
        """
        Retrieve MT5 symbol metadata.
        """

        return mt5.symbol_info(symbol)

    @staticmethod
    def symbol_select(
        symbol: str,
        select: bool = True,
    ) -> bool:
        """
        Enable or disable a symbol in the MT5 terminal's
        Market Watch.
        """

        return bool(
            mt5.symbol_select(
                symbol,
                select,
            )
        )

    @staticmethod
    def last_error() -> Any:
        """
        Return the latest MT5 terminal error.
        """

        return mt5.last_error()

    def pending(
        self,
        symbol: str,
        volume: float,
        order_type: int,
        price: float,
        sl: float | None = None,
        tp: float | None = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "",
    ) -> Any:
        """
        Submit a pending-order request to MT5.

        Pending orders use ORDER_FILLING_RETURN according to
        the MT5 execution model.
        """

        order_filling_return = getattr(
            mt5,
            "ORDER_FILLING_RETURN",
            2,
        )

        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": magic,
            "comment": str(comment)[:31],
            "type_filling": order_filling_return,
        }

        if sl is not None:
            request["sl"] = sl

        if tp is not None:
            request["tp"] = tp

        return self.send(request)
