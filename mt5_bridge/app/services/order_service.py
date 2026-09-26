from __future__ import annotations

from typing import Any

import MetaTrader5 as mt5

from app.broker.orders import OrderBroker


class OrderService:
    """
    Application service for MT5 order operations.

    This service translates validated bridge requests into MT5 trade
    requests and normalizes MT5 responses into the bridge response
    contract.

    MT5 distinguishes between:

        order
            Broker order/ticket.

        deal
            Executed transaction.

        position
            Resulting open position.

    These identifiers represent different MT5 objects and must never
    be conflated.
    """

    def __init__(self) -> None:
        self.broker = OrderBroker()

    # ------------------------------------------------------------------
    # Market orders
    # ------------------------------------------------------------------

    def send_order(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Submit a market order to MT5.

        For market execution, price may be omitted by the caller.
        In that case MT5 receives the request without an explicit
        price and uses the current market price according to the
        configured execution mode.
        """

        mt5_request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request["symbol"],
            "volume": request["volume"],
            "type": request["order_type"],
            "deviation": request.get("deviation", 20),
            "magic": request.get("magic", 0),
            "comment": str(request.get("comment", "AQE"))[:31],
        }

        price = request.get("price")

        if price is not None:
            mt5_request["price"] = price

        sl = request.get("sl")
        tp = request.get("tp")

        if sl is not None:
            mt5_request["sl"] = sl

        if tp is not None:
            mt5_request["tp"] = tp

        result = self.broker.send(mt5_request)

        if result is None:
            raise RuntimeError(
                "Order submission failed. " f"MT5 error: {self.broker.last_error()}"
            )

        self._ensure_market_order_accepted(result)

        return self._normalize_result(result)

    # ------------------------------------------------------------------
    # Order validation
    # ------------------------------------------------------------------

    def check_order(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """
        Validate an MT5 trade request without submitting it.
        """

        result = self.broker.check(request)

        if result is None:
            return None

        return result._asdict()

    # ------------------------------------------------------------------
    # Broker orders
    # ------------------------------------------------------------------

    def list_orders(self) -> list[dict[str, Any]]:
        """
        Return all currently active/pending MT5 orders.
        """

        orders = self.broker.orders()

        if orders is None:
            return []

        return [order._asdict() for order in orders]

    def get_order(self, ticket: int) -> dict[str, Any] | None:
        """
        Retrieve a specific MT5 order by broker order ticket.
        """

        orders = self.broker.order(ticket)

        if not orders:
            return None

        return orders[0]._asdict()

    # ------------------------------------------------------------------
    # Pending orders
    # ------------------------------------------------------------------

    def create_pending_order(
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
    ) -> dict[str, Any]:
        """
        Create a pending MT5 order.

        A successfully placed pending order should have an order ID.
        It normally does not have an execution deal or resulting
        position yet.
        """

        result = self.broker.pending(
            symbol=symbol,
            volume=volume,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            deviation=deviation,
            magic=magic,
            comment=str(comment)[:31],
        )

        if result is None:
            raise RuntimeError(
                "Pending order submission failed. "
                f"MT5 error: {self.broker.last_error()}"
            )

        self._ensure_pending_order_accepted(result)

        return self._normalize_pending_result(
            result=result,
            symbol=symbol,
            order_type=order_type,
            requested_sl=sl,
            requested_tp=tp,
        )

    # ------------------------------------------------------------------
    # Response normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        """
        Normalize an MT5 MqlTradeResult into the bridge response
        contract.

        `result.order`, `result.deal`, and `result.position` are
        deliberately mapped to separate fields.
        """

        request = getattr(result, "request", None)

        return {
            "order_id": getattr(result, "order", None),
            "deal_id": getattr(result, "deal", None),
            "position_id": getattr(result, "position", None),
            "symbol": (
                getattr(request, "symbol", None)
                or getattr(result, "symbol", None)
                or ""
            ),
            "volume": getattr(result, "volume", 0.0),
            "price_open": getattr(result, "price", 0.0),
            "sl": getattr(request, "sl", None),
            "tp": getattr(request, "tp", None),
            "order_type": getattr(request, "type", None),
            "state": getattr(result, "retcode", None),
            "comment": getattr(result, "comment", ""),
        }

    @staticmethod
    def _normalize_pending_result(
        *,
        result: Any,
        symbol: str,
        order_type: int,
        requested_sl: float | None,
        requested_tp: float | None,
    ) -> dict[str, Any]:
        """
        Normalize a pending-order MT5 response.

        The requested SL/TP values are retained because the raw
        MqlTradeResult does not necessarily expose them directly.
        """

        order_id = getattr(result, "order", None)

        return {
            "order_id": order_id,
            "deal_id": getattr(result, "deal", None),
            "position_id": getattr(result, "position", None),
            "symbol": symbol,
            "volume": getattr(result, "volume", 0.0),
            "price_open": getattr(result, "price", 0.0),
            "sl": requested_sl,
            "tp": requested_tp,
            "order_type": order_type,
            "state": getattr(result, "retcode", None),
            "comment": getattr(result, "comment", ""),
        }

    # ------------------------------------------------------------------
    # MT5 result validation
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_market_order_accepted(result: Any) -> None:
        """
        Ensure MT5 accepted a market-order request.

        TRADE_RETCODE_DONE means the requested trade operation
        completed successfully.

        DONE_PARTIAL is also an accepted execution result because
        the broker may execute only part of the requested volume.
        """

        accepted_codes = {
            mt5.TRADE_RETCODE_DONE,
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1),
        }

        retcode = getattr(result, "retcode", None)

        if retcode not in accepted_codes:
            raise RuntimeError(
                "Order submission failed. "
                f"MT5 retcode: {retcode}, "
                f"comment: {getattr(result, 'comment', '')}"
            )

    @staticmethod
    def _ensure_pending_order_accepted(result: Any) -> None:
        """
        Ensure MT5 accepted a pending-order request.

        MT5 can report either:

            TRADE_RETCODE_PLACED
                The pending order was placed.

            TRADE_RETCODE_DONE
                The trade operation completed successfully.

        Both are valid successful outcomes for the bridge.
        """

        accepted_codes = {
            mt5.TRADE_RETCODE_PLACED,
            mt5.TRADE_RETCODE_DONE,
        }

        retcode = getattr(result, "retcode", None)

        if retcode not in accepted_codes:
            raise RuntimeError(
                "Pending order submission failed. "
                f"MT5 retcode: {retcode}, "
                f"comment: {getattr(result, 'comment', '')}"
            )
