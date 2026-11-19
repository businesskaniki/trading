from __future__ import annotations

import math
from typing import Any

import MetaTrader5 as mt5

from app.broker.orders import OrderBroker
from app.core.logging import logger
from app.schemas.order import OrderOutcome, OrderResponse


class OrderService:
    """
    Application service for MT5 order operations.

    Responsibilities:
        - Build MT5 market and pending-order requests.
        - Validate broker symbols and filling policies.
        - Submit orders through OrderBroker.
        - Classify broker outcomes without inventing fills.
        - Normalize MqlTradeResult into the bridge response contract.

    Important:
        - NOT_SUBMITTED means the broker submission boundary was not
          crossed because preflight failed.
        - UNKNOWN means the outcome cannot be established safely.
        - PLACED means the broker reports an order was placed.
        - FILLED/PARTIALLY_FILLED require broker-confirmed deal evidence.
        - REJECTED means a known return code establishes non-execution.

    This service does not persist AQE database records or retry orders.
    """

    MARKET_BUY = 0
    MARKET_SELL = 1

    def __init__(self) -> None:
        self.broker = OrderBroker()

    # ==============================================================
    # MARKET ORDERS
    # ==============================================================

    def send_order(
        self,
        request: dict[str, Any],
    ) -> OrderResponse:
        """
        Submit a market order.

        A missing result or exception after entering order_send is
        treated as UNKNOWN because the broker may have processed
        the request before the failure became visible.
        """

        symbol = str(request.get("symbol", "")).strip()

        try:
            order_type = int(request["order_type"])
            requested_volume = float(request["volume"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "Market order requires a valid order_type and volume."
            ) from exc

        if not symbol:
            raise ValueError("Order symbol cannot be empty.")

        if not math.isfinite(requested_volume) or requested_volume <= 0:
            raise ValueError("Order volume must be greater than zero.")

        if order_type not in {
            self.MARKET_BUY,
            self.MARKET_SELL,
        }:
            raise ValueError("Market orders must use MT5 BUY=0 or SELL=1 order types.")

        requested_price: float | None = None
        sl: float | None = None
        tp: float | None = None

        # ----------------------------------------------------------
        # Preflight: no trading request has been submitted yet.
        # ----------------------------------------------------------

        try:
            symbol_info = self._ensure_symbol_ready(symbol)
            type_filling = self._resolve_market_filling_mode(symbol_info)

            raw_price = request.get("price")
            if raw_price is not None:
                requested_price = float(raw_price)

                if not math.isfinite(requested_price) or requested_price <= 0:
                    raise ValueError("Market order price must be greater than zero.")

            raw_sl = request.get("sl")
            if raw_sl is not None:
                sl = float(raw_sl)

                if not math.isfinite(sl) or sl <= 0:
                    raise ValueError("Stop loss must be greater than zero.")

            raw_tp = request.get("tp")
            if raw_tp is not None:
                tp = float(raw_tp)

                if not math.isfinite(tp) or tp <= 0:
                    raise ValueError("Take profit must be greater than zero.")

            mt5_request: dict[str, Any] = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": requested_volume,
                "type": order_type,
                "deviation": int(request.get("deviation", 20)),
                "magic": int(request.get("magic", 0)),
                "comment": str(request.get("comment", "AQE"))[:31],
                "type_filling": type_filling,
            }

            if requested_price is not None:
                mt5_request["price"] = requested_price

            if sl is not None:
                mt5_request["sl"] = sl

            if tp is not None:
                mt5_request["tp"] = tp

        except Exception as exc:
            return self._not_submitted(
                symbol=symbol,
                order_type=order_type,
                requested_volume=requested_volume,
                requested_price=requested_price,
                sl=sl,
                tp=tp,
                message=("Preflight failed; order was not submitted: " f"{exc}"),
            )

        # ----------------------------------------------------------
        # MT5 MARKET ORDER DIAGNOSTICS
        # Diagnostic only: does not modify or block submission.
        # ----------------------------------------------------------

        diagnostics: dict[str, Any] = {
            "request": dict(mt5_request),
            "symbol_constraints": {
                "digits": getattr(symbol_info, "digits", None),
                "point": getattr(symbol_info, "point", None),
                "trade_tick_size": getattr(symbol_info, "trade_tick_size", None),
                "trade_stops_level": getattr(symbol_info, "trade_stops_level", None),
                "trade_freeze_level": getattr(symbol_info, "trade_freeze_level", None),
                "trade_exemode": getattr(symbol_info, "trade_exemode", None),
                "trade_mode": getattr(symbol_info, "trade_mode", None),
                "filling_mode": getattr(symbol_info, "filling_mode", None),
            },
        }

        # Capture the latest Bid/Ask immediately before submission.
        try:
            tick = self.broker.symbol_info_tick(symbol)

            if tick is None:
                diagnostics["tick"] = None
                diagnostics["tick_error"] = self.broker.last_error()
            else:
                diagnostics["tick"] = {
                    "bid": getattr(tick, "bid", None),
                    "ask": getattr(tick, "ask", None),
                    "last": getattr(tick, "last", None),
                    "time": getattr(tick, "time", None),
                    "time_msc": getattr(tick, "time_msc", None),
                }

        except Exception as exc:
            diagnostics["tick_exception"] = repr(exc)

        # Validate the exact request without submitting it.
        try:
            check_result = self.check_order(mt5_request)
            diagnostics["order_check"] = check_result

            if check_result is None:
                diagnostics["order_check_error"] = self.broker.last_error()

        except Exception as exc:
            diagnostics["order_check_exception"] = repr(exc)

        logger.info(
            "MT5_MARKET_ORDER_DIAGNOSTICS %s",
            diagnostics,
        )

        # ----------------------------------------------------------
        # Submission boundary.
        #
        # From this point onward, an exception or missing result
        # cannot safely be interpreted as proof of non-execution.
        # ----------------------------------------------------------

        try:
            result = self.broker.send(mt5_request)

        except Exception as exc:
            return self._unknown_outcome(
                symbol=symbol,
                order_type=order_type,
                requested_volume=requested_volume,
                requested_price=requested_price,
                sl=sl,
                tp=tp,
                message=f"MT5 submission outcome is unknown: {exc}",
            )

        if result is None:
            return self._unknown_outcome(
                symbol=symbol,
                order_type=order_type,
                requested_volume=requested_volume,
                requested_price=requested_price,
                sl=sl,
                tp=tp,
                message=(
                    "MT5 returned no trade result. "
                    f"Terminal error: {self.broker.last_error()}"
                ),
            )

        return self._normalize_result(
            result=result,
            symbol=symbol,
            order_type=order_type,
            requested_volume=requested_volume,
            requested_price=requested_price,
            requested_sl=sl,
            requested_tp=tp,
            is_pending=False,
        )

    # ==============================================================
    # PENDING ORDERS
    # ==============================================================

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
    ) -> OrderResponse:
        """
        Submit a LIMIT or STOP order.

        A pending order is not considered filled simply because it
        was accepted by the broker.
        """

        symbol = str(symbol).strip()

        try:
            volume = float(volume)
            price = float(price)
            order_type = int(order_type)

            if sl is not None:
                sl = float(sl)

            if tp is not None:
                tp = float(tp)

        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid pending-order numeric parameters.") from exc

        if not symbol:
            raise ValueError("Order symbol cannot be empty.")

        if not math.isfinite(volume) or volume <= 0:
            raise ValueError("Order volume must be greater than zero.")

        if not math.isfinite(price) or price <= 0:
            raise ValueError("Pending order price must be greater than zero.")

        pending_types = {
            mt5.ORDER_TYPE_BUY_LIMIT,
            mt5.ORDER_TYPE_SELL_LIMIT,
            mt5.ORDER_TYPE_BUY_STOP,
            mt5.ORDER_TYPE_SELL_STOP,
        }

        if order_type not in pending_types:
            raise ValueError(
                "Pending orders must use BUY_LIMIT, SELL_LIMIT, "
                "BUY_STOP or SELL_STOP."
            )

        if sl is not None and (not math.isfinite(sl) or sl <= 0):
            raise ValueError("Stop loss must be greater than zero.")

        if tp is not None and (not math.isfinite(tp) or tp <= 0):
            raise ValueError("Take profit must be greater than zero.")

        # ----------------------------------------------------------
        # Preflight: prepare the symbol before submitting the order.
        # ----------------------------------------------------------

        try:
            self._ensure_symbol_ready(symbol)

        except Exception as exc:
            return self._not_submitted(
                symbol=symbol,
                order_type=order_type,
                requested_volume=volume,
                requested_price=price,
                sl=sl,
                tp=tp,
                message=(
                    "Preflight failed; pending order was not " f"submitted: {exc}"
                ),
            )

        # ----------------------------------------------------------
        # Submission boundary.
        # ----------------------------------------------------------

        try:
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

        except Exception as exc:
            return self._unknown_outcome(
                symbol=symbol,
                order_type=order_type,
                requested_volume=volume,
                requested_price=price,
                sl=sl,
                tp=tp,
                message=("Pending-order outcome is unknown: " f"{exc}"),
            )

        if result is None:
            return self._unknown_outcome(
                symbol=symbol,
                order_type=order_type,
                requested_volume=volume,
                requested_price=price,
                sl=sl,
                tp=tp,
                message=(
                    "MT5 returned no pending-order result. "
                    f"Terminal error: {self.broker.last_error()}"
                ),
            )

        return self._normalize_result(
            result=result,
            symbol=symbol,
            order_type=order_type,
            requested_volume=volume,
            requested_price=price,
            requested_sl=sl,
            requested_tp=tp,
            is_pending=True,
        )

    # ==============================================================
    # SYMBOL PREPARATION
    # ==============================================================

    def _ensure_symbol_ready(
        self,
        symbol: str,
    ) -> Any:
        """
        Retrieve symbol metadata and select the symbol in Market Watch
        if required.
        """

        symbol_info = self.broker.symbol_info(symbol)

        if symbol_info is None:
            raise RuntimeError(
                "MT5 symbol is unavailable. "
                f"symbol={symbol}; "
                f"error={self.broker.last_error()}"
            )

        visible = getattr(symbol_info, "visible", True)

        if not visible:
            selected = self.broker.symbol_select(
                symbol,
                True,
            )

            if not selected:
                raise RuntimeError(
                    "Unable to select MT5 symbol in Market Watch. "
                    f"symbol={symbol}; "
                    f"error={self.broker.last_error()}"
                )

            symbol_info = self.broker.symbol_info(symbol)

            if symbol_info is None:
                raise RuntimeError(
                    "MT5 symbol became unavailable after selection. " f"symbol={symbol}"
                )

        return symbol_info

    # ==============================================================
    # MARKET FILLING POLICY
    # ==============================================================

    @staticmethod
    def _resolve_market_filling_mode(
        symbol_info: Any,
    ) -> int:
        """
        Select a filling mode supported by the symbol.

        ORDER_FILLING_RETURN is not valid for Market Execution.
        For that mode, FOK or IOC must be available.
        """

        filling_mode = getattr(
            symbol_info,
            "filling_mode",
            None,
        )

        execution_mode = getattr(
            symbol_info,
            "trade_exemode",
            None,
        )

        if filling_mode is None:
            raise RuntimeError("MT5 symbol does not expose a filling mode.")

        symbol_filling_fok = getattr(
            mt5,
            "SYMBOL_FILLING_FOK",
            1,
        )

        symbol_filling_ioc = getattr(
            mt5,
            "SYMBOL_FILLING_IOC",
            2,
        )

        order_filling_fok = getattr(
            mt5,
            "ORDER_FILLING_FOK",
            0,
        )

        order_filling_ioc = getattr(
            mt5,
            "ORDER_FILLING_IOC",
            1,
        )

        order_filling_return = getattr(
            mt5,
            "ORDER_FILLING_RETURN",
            2,
        )

        market_execution = getattr(
            mt5,
            "SYMBOL_TRADE_EXECUTION_MARKET",
            2,
        )

        if execution_mode == market_execution:
            if filling_mode & symbol_filling_fok:
                return order_filling_fok

            if filling_mode & symbol_filling_ioc:
                return order_filling_ioc

            raise RuntimeError(
                "MT5 symbol does not allow FOK or IOC filling "
                "for Market Execution. "
                f"filling_mode={filling_mode}"
            )

        if filling_mode & symbol_filling_fok:
            return order_filling_fok

        if filling_mode & symbol_filling_ioc:
            return order_filling_ioc

        return order_filling_return

    # ==============================================================
    # ORDER VALIDATION
    # ==============================================================

    def check_order(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Validate a trade request without submitting it."""

        result = self.broker.check(request)

        if result is None:
            return None

        return result._asdict()

    # ==============================================================
    # ACTIVE BROKER ORDERS
    # ==============================================================

    def list_orders(self) -> list[dict[str, Any]]:
        """Return active/pending MT5 orders."""

        orders = self.broker.orders()

        if orders is None:
            return []

        return [order._asdict() for order in orders]

    def get_order(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        """Retrieve an active MT5 order by ticket."""

        orders = self.broker.order(ticket)

        if not orders:
            return None

        return orders[0]._asdict()

    # ==============================================================
    # RESULT CLASSIFICATION
    # ==============================================================

    @staticmethod
    def _positive_id(
        value: Any,
    ) -> int | None:
        """Normalize an optional positive broker ticket."""

        if value is None or isinstance(value, bool):
            return None

        try:
            result = int(value)

        except (TypeError, ValueError, OverflowError):
            return None

        return result if result > 0 else None

    @staticmethod
    def _optional_int(
        value: Any,
    ) -> int | None:
        """Normalize an optional integer without assuming it is positive."""

        if value is None or isinstance(value, bool):
            return None

        try:
            return int(value)

        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _positive_float(
        value: Any,
    ) -> float | None:
        """Return a finite, strictly positive float or None."""

        if value is None or isinstance(value, bool):
            return None

        try:
            result = float(value)

        except (TypeError, ValueError, OverflowError):
            return None

        if not math.isfinite(result) or result <= 0:
            return None

        return result

    def _classify_result(
        self,
        *,
        result: Any,
        requested_volume: float,
        is_pending: bool,
    ) -> OrderOutcome:
        """
        Interpret MT5's retcode using broker-confirmed evidence.

        Unknown return codes remain UNKNOWN. A non-exceptional API
        call is not, by itself, proof of a fill.
        """

        retcode = self._optional_int(getattr(result, "retcode", None))

        order_id = self._positive_id(getattr(result, "order", None))

        deal_id = self._positive_id(getattr(result, "deal", None))

        executed_volume = self._positive_float(getattr(result, "volume", None))

        execution_price = self._positive_float(getattr(result, "price", None))

        placed_code = getattr(
            mt5,
            "TRADE_RETCODE_PLACED",
            10008,
        )

        done_code = getattr(
            mt5,
            "TRADE_RETCODE_DONE",
            10009,
        )

        partial_code = getattr(
            mt5,
            "TRADE_RETCODE_DONE_PARTIAL",
            10010,
        )

        # A placed order is not necessarily a filled order.
        if retcode == placed_code:
            if order_id is not None:
                return OrderOutcome.PLACED

            return OrderOutcome.UNKNOWN

        # Explicit partial-completion response. Require evidence
        # of an actual deal, positive volume and an execution price.
        if retcode == partial_code:
            if (
                deal_id is not None
                and executed_volume is not None
                and execution_price is not None
                and executed_volume < requested_volume
                and not math.isclose(
                    executed_volume,
                    requested_volume,
                    rel_tol=1e-8,
                    abs_tol=1e-8,
                )
            ):
                return OrderOutcome.PARTIALLY_FILLED

            return OrderOutcome.UNKNOWN

        # Completed request: distinguish actual execution from a
        # pending order that was accepted without an executed deal.
        if retcode == done_code:
            if (
                deal_id is not None
                and executed_volume is not None
                and execution_price is not None
            ):
                if math.isclose(
                    executed_volume,
                    requested_volume,
                    rel_tol=1e-8,
                    abs_tol=1e-8,
                ):
                    return OrderOutcome.FILLED

                if (
                    0 < executed_volume < requested_volume
                    and executed_volume < requested_volume
                    and not math.isclose(
                        executed_volume,
                        requested_volume,
                        rel_tol=1e-8,
                        abs_tol=1e-8,
                    )
                ):
                    return OrderOutcome.PARTIALLY_FILLED

                # The result volume exceeds the requested volume or
                # the result does not agree with the requested order.
                return OrderOutcome.UNKNOWN

            if is_pending and order_id is not None and deal_id is None:
                return OrderOutcome.PLACED

            return OrderOutcome.UNKNOWN

        # Known broker responses indicating the request was not
        # executed. This is deliberately a conservative allowlist.
        rejected_codes = {
            10004,  # REQUOTE
            10006,  # REJECT
            10007,  # CANCEL
            10013,  # INVALID
            10014,  # INVALID_VOLUME
            10015,  # INVALID_PRICE
            10016,  # INVALID_STOPS
            10017,  # TRADE_DISABLED
            10018,  # MARKET_CLOSED
            10019,  # NO_MONEY
            10020,  # PRICE_CHANGED
            10021,  # NO_QUOTES
            10022,  # INVALID_EXPIRATION
            10024,  # TOO_MANY_REQUESTS
            10026,  # SERVER_DISABLES_AT
            10027,  # CLIENT_DISABLES_AT
            10030,  # INVALID_FILL
            10032,  # ONLY_REAL
            10033,  # LIMIT_ORDERS
            10034,  # LIMIT_VOLUME
            10035,  # INVALID_ORDER
            10042,  # LONG_ONLY
            10043,  # SHORT_ONLY
            10044,  # CLOSE_ONLY
            10045,  # FIFO_CLOSE
            10046,  # HEDGE_PROHIBITED
        }

        if retcode in rejected_codes:
            return OrderOutcome.REJECTED

        # ERROR, TIMEOUT, CONNECTION and unrecognized codes must not
        # be turned into rejection or success without more evidence.
        return OrderOutcome.UNKNOWN

    # ==============================================================
    # RESULT NORMALIZATION
    # ==============================================================

    def _normalize_result(
        self,
        *,
        result: Any,
        symbol: str,
        order_type: int,
        requested_volume: float,
        requested_price: float | None,
        requested_sl: float | None,
        requested_tp: float | None,
        is_pending: bool,
    ) -> OrderResponse:
        """
        Convert MqlTradeResult to the bridge response contract.

        MqlTradeResult does not provide a position identifier as a
        standard field. Position identity must be resolved from
        broker position/deal data, so position_id remains None here.
        """

        retcode = self._optional_int(getattr(result, "retcode", None))

        order_id = self._positive_id(getattr(result, "order", None))

        deal_id = self._positive_id(getattr(result, "deal", None))

        raw_volume = self._positive_float(getattr(result, "volume", None))

        raw_price = self._positive_float(getattr(result, "price", None))

        outcome = self._classify_result(
            result=result,
            requested_volume=requested_volume,
            is_pending=is_pending,
        )

        has_confirmed_execution = outcome in {
            OrderOutcome.FILLED,
            OrderOutcome.PARTIALLY_FILLED,
        }

        executed_volume = raw_volume if has_confirmed_execution else None

        execution_price = raw_price if has_confirmed_execution else None

        comment = str(getattr(result, "comment", "") or "").strip()

        if not comment:
            messages = {
                OrderOutcome.NOT_SUBMITTED: "Order was not submitted.",
                OrderOutcome.PLACED: "Broker placed the order; execution is not yet confirmed.",
                OrderOutcome.FILLED: "Broker confirmed full execution.",
                OrderOutcome.PARTIALLY_FILLED: "Broker confirmed partial execution.",
                OrderOutcome.REJECTED: f"Broker rejected the request (retcode={retcode}).",
                OrderOutcome.UNKNOWN: f"Broker outcome could not be confirmed (retcode={retcode}).",
            }

            comment = messages[outcome]

        return OrderResponse(
            outcome=outcome,
            symbol=symbol,
            order_type=order_type,
            requested_volume=requested_volume,
            executed_volume=executed_volume,
            requested_price=requested_price,
            execution_price=execution_price,
            order_id=order_id,
            deal_id=deal_id,
            position_id=None,
            retcode=retcode,
            request_id=self._optional_int(getattr(result, "request_id", None)),
            retcode_external=self._optional_int(
                getattr(result, "retcode_external", None)
            ),
            sl=requested_sl,
            tp=requested_tp,
            comment=comment,
            # Temporary legacy fields.
            # New AQE logic must use the explicit fields above.
            volume=raw_volume,
            price_open=raw_price,
            state=retcode,
        )

    # ==============================================================
    # PRE-SUBMISSION FAILURE RESPONSE
    # ==============================================================

    @staticmethod
    def _not_submitted(
        *,
        symbol: str,
        order_type: int,
        requested_volume: float,
        requested_price: float | None,
        sl: float | None,
        tp: float | None,
        message: str,
    ) -> OrderResponse:
        """
        Represent a failure known to have occurred before the broker
        submission boundary was crossed.
        """

        return OrderResponse(
            outcome=OrderOutcome.NOT_SUBMITTED,
            symbol=symbol,
            order_type=order_type,
            requested_volume=requested_volume,
            executed_volume=None,
            requested_price=requested_price,
            execution_price=None,
            order_id=None,
            deal_id=None,
            position_id=None,
            retcode=None,
            request_id=None,
            retcode_external=None,
            sl=sl,
            tp=tp,
            comment=message,
        )

    # ==============================================================
    # UNCERTAIN SUBMISSION RESPONSE
    # ==============================================================

    @staticmethod
    def _unknown_outcome(
        *,
        symbol: str,
        order_type: int,
        requested_volume: float,
        requested_price: float | None,
        sl: float | None,
        tp: float | None,
        message: str,
    ) -> OrderResponse:
        """
        Represent a request whose broker outcome cannot be confirmed.

        No broker execution volume or price is fabricated.
        """

        return OrderResponse(
            outcome=OrderOutcome.UNKNOWN,
            symbol=symbol,
            order_type=order_type,
            requested_volume=requested_volume,
            executed_volume=None,
            requested_price=requested_price,
            execution_price=None,
            order_id=None,
            deal_id=None,
            position_id=None,
            retcode=None,
            request_id=None,
            retcode_external=None,
            sl=sl,
            tp=tp,
            comment=message,
        )
