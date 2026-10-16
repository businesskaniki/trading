from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerDataError,
    BrokerOrderError,
    BrokerPositionError,
)
from app.core.config import settings
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)
from .client import MT5Client


class MT5OrderMapper:
    """
    Converts broker-agnostic AQE ExecutionOrder objects
    into MT5 Bridge order payloads.
    """

    MARKET_BUY = 0
    MARKET_SELL = 1
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5

    @staticmethod
    def to_mt5(
        order: ExecutionOrder,
    ) -> dict[str, Any]:
        if order.volume <= 0:
            raise BrokerOrderError("Order volume must be greater than zero.")
        symbol = str(order.symbol).strip()
        if not symbol:
            raise BrokerOrderError("Order symbol cannot be empty.")
        payload: dict[str, Any] = {
            "symbol": symbol,
            "volume": float(order.volume),
            "deviation": order.deviation,
            "magic": order.magic_number,
            "comment": (str(order.comment).strip()[:31] if order.comment else "AQE"),
        }
        # ------------------------------------------------------
        # MARKET
        # ------------------------------------------------------
        if order.order_type == OrderType.MARKET:
            if order.side == OrderSide.BUY:
                payload["order_type"] = MT5OrderMapper.MARKET_BUY
            elif order.side == OrderSide.SELL:
                payload["order_type"] = MT5OrderMapper.MARKET_SELL
            else:
                raise BrokerOrderError(f"Unsupported market order side: {order.side}")
        # ------------------------------------------------------
        # LIMIT
        # ------------------------------------------------------
        elif order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise BrokerOrderError("LIMIT order requires a price.")
            if order.side == OrderSide.BUY:
                payload["order_type"] = MT5OrderMapper.BUY_LIMIT
            elif order.side == OrderSide.SELL:
                payload["order_type"] = MT5OrderMapper.SELL_LIMIT
            else:
                raise BrokerOrderError(f"Unsupported limit order side: {order.side}")
            payload["price"] = float(order.price)
        # ------------------------------------------------------
        # STOP
        # ------------------------------------------------------
        elif order.order_type == OrderType.STOP:
            if order.price is None:
                raise BrokerOrderError("STOP order requires a price.")
            if order.side == OrderSide.BUY:
                payload["order_type"] = MT5OrderMapper.BUY_STOP
            elif order.side == OrderSide.SELL:
                payload["order_type"] = MT5OrderMapper.SELL_STOP
            else:
                raise BrokerOrderError(f"Unsupported stop order side: {order.side}")
            payload["price"] = float(order.price)
        else:
            raise BrokerOrderError(f"Unsupported order type: {order.order_type}")
        # ------------------------------------------------------
        # STOP LOSS
        # ------------------------------------------------------
        if order.stop_loss is not None:
            payload["sl"] = float(order.stop_loss)
        # ------------------------------------------------------
        # TAKE PROFIT
        # ------------------------------------------------------
        if order.take_profit is not None:
            payload["tp"] = float(order.take_profit)
        return payload


class MT5Adapter(BrokerAdapter):
    """
    AQE MetaTrader 5 broker adapter.
    Responsibilities:
        - Communicate with the MT5 Bridge.
        - Translate AQE orders into MT5 payloads.
        - Normalize broker responses.
        - Normalize broker-specific historical order states.
        - Expose broker operations through the AQE
          broker interface.
    It does NOT:
        - Create database records.
        - Run strategies.
        - Perform risk calculations.
        - Generate trading signals.
        - Manage user authentication.
    Those responsibilities belong to higher layers.
    """

    BROKER_NAME = "MT5"

    # ==========================================================
    # MT5 ORDER HISTORY STATES

    # ==========================================================
    #
    # These values correspond to the MetaTrader 5
    # ENUM_ORDER_STATE values returned by the bridge.
    #
    # They are intentionally isolated here.
    #
    # The rest of AQE must NOT depend on MT5 numeric values.

    # ==========================================================
    ORDER_STATE_STARTED = 0
    ORDER_STATE_PLACED = 1
    ORDER_STATE_CANCELED = 2
    ORDER_STATE_PARTIAL = 3
    ORDER_STATE_FILLED = 4
    ORDER_STATE_REJECTED = 5
    ORDER_STATE_EXPIRED = 6
    ORDER_STATE_REQUEST_ADD = 7
    ORDER_STATE_REQUEST_MODIFY = 8
    ORDER_STATE_REQUEST_CANCEL = 9
    # MT5 trade-server return codes relevant to order execution.
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_REJECT = 10006
    TRADE_RETCODE_CANCEL = 10007
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_ERROR = 10011
    TRADE_RETCODE_TIMEOUT = 10012
    TRADE_RETCODE_CONNECTION = 10031
    # Explicit responses indicating the requested trade did not complete.
    # Unknown and transport-related outcomes remain UNKNOWN for reconciliation.
    TRADE_RETCODES_REJECTED = frozenset(
        {
            10004,
            10006,
            10007,
            10013,
            10014,
            10015,
            10016,
            10017,
            10018,
            10019,
            10020,
            10021,
            10022,
            10024,
            10026,
            10027,
            10028,
            10029,
            10030,
            10032,
            10033,
            10034,
            10035,
            10036,
            10038,
            10039,
            10040,
            10041,
            10042,
            10043,
            10044,
            10045,
            10046,
        }
    )

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
        account_id: str | None = None,
    ) -> None:
        self.client = MT5Client(
            bridge_url=bridge_url,
            bridge_token=settings.MT5_BRIDGE_TOKEN,
            timeout=timeout,
        )
        self.bridge_url = bridge_url.rstrip("/")
        self.timeout = timeout
        self.account_id = account_id

    # ==========================================================
    # CONNECTION

    # ==========================================================

    async def connect(
        self,
        credentials: dict[str, Any] | None = None,
    ):
        """
        Connect the MT5 Bridge to the requested MT5 account.
        """
        try:
            return await self.client.post(
                "/connection/connect",
                credentials,
            )
        except RuntimeError as exc:
            raise BrokerConnectionError(f"Failed to connect to MT5: {exc}") from exc

    async def disconnect(self):
        """
        Disconnect the MT5 Bridge from the current MT5 account.
        """
        try:
            return await self.client.post("/connection/disconnect")
        except RuntimeError as exc:
            raise BrokerConnectionError(
                f"Failed to disconnect from MT5: {exc}"
            ) from exc

    async def connection_status(self):
        """
        Return current MT5 bridge connection status.
        """
        try:
            return await self.client.get("/connection/status")
        except RuntimeError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 connection status: {exc}"
            ) from exc

    # ==========================================================
    # ACCOUNT

    # ==========================================================

    async def get_account(self):
        """
        Retrieve account information from MT5.
        """
        try:
            return await self.client.get("/account")
        except RuntimeError as exc:
            raise BrokerDataError(f"Failed to retrieve MT5 account: {exc}") from exc

    # ==========================================================
    # SYMBOLS

    # ==========================================================

    async def get_symbols(self):
        """
        Retrieve available symbols from MT5.
        """
        try:
            return await self.client.get("/symbols")
        except RuntimeError as exc:
            raise BrokerDataError(f"Failed to retrieve MT5 symbols: {exc}") from exc

    async def get_symbol(
        self,
        symbol: str,
    ):
        """
        Retrieve metadata for a single symbol.
        """
        if not symbol:
            raise BrokerDataError("Symbol cannot be empty.")
        try:
            return await self.client.get(f"/symbols/{symbol}")
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 symbol {symbol}: {exc}"
            ) from exc

    async def get_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Retrieve the latest valid broker tick.
        The MT5 Bridge exposes live ticks through:
            /market-data/tick/{symbol}
        """
        symbol = str(symbol).strip()
        if not symbol:
            raise BrokerDataError("Symbol cannot be empty.")
        try:
            tick = await self.client.get(f"/market-data/tick/{symbol}")
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve tick for {symbol}: {exc}"
            ) from exc
        if not isinstance(tick, dict):
            raise BrokerDataError(
                f"Invalid tick response for {symbol}: "
                f"expected object, got {type(tick).__name__}."
            )
        bid_raw = tick.get("bid")
        ask_raw = tick.get("ask")
        if bid_raw is None or ask_raw is None:
            raise BrokerDataError(f"Tick for {symbol} is missing bid or ask: {tick!r}")
        try:
            bid = Decimal(str(bid_raw))
            ask = Decimal(str(ask_raw))
        except (
            TypeError,
            ValueError,
            InvalidOperation,
        ) as exc:
            raise BrokerDataError(
                f"Invalid tick values returned for {symbol}: "
                f"bid={bid_raw!r} ask={ask_raw!r}"
            ) from exc
        if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0:
            raise BrokerDataError(
                f"Invalid tick values returned for {symbol}: " f"bid={bid} ask={ask}"
            )
        if ask < bid:
            raise BrokerDataError(
                f"Invalid tick for {symbol}: " f"ask={ask} < bid={bid}"
            )
        return {
            **tick,
            "bid": bid,
            "ask": ask,
        }

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ):
        """
        Retrieve recent OHLC candles for a symbol.
        """
        if not symbol:
            raise BrokerDataError("Symbol cannot be empty.")
        try:
            return await self.client.get(
                f"/symbols/{symbol}/candles",
                params={
                    "timeframe": timeframe,
                    "count": count,
                },
            )
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve candles for {symbol}: {exc}"
            ) from exc

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        """Parse an integer without silently truncating invalid values."""
        if value is None or isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            return None
        if not number.is_finite():
            return None
        if number != number.to_integral_value():
            return None
        return int(number)

    @classmethod
    def _broker_identifier(
        cls,
        response: dict[str, Any],
        keys: tuple[str, ...],
    ) -> int | None:
        """Extract a valid positive identifier from broker response aliases."""
        for key in keys:
            parsed = cls._optional_int(response.get(key))
            if parsed is not None and parsed > 0:
                return parsed
        return None

    @staticmethod
    def _positive_decimal(value: Any) -> Decimal | None:
        """Parse a positive finite broker-confirmed price or volume."""
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            return None
        if not parsed.is_finite() or parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _first_value(
        response: dict[str, Any],
        keys: tuple[str, ...],
    ) -> Any:
        """Return the first non-null value for a sequence of response keys."""
        for key in keys:
            value = response.get(key)
            if value is not None:
                return value
        return None

    @classmethod
    def _confirmed_fill_status(
        cls,
        *,
        requested_volume: Decimal,
        executed_volume: Decimal | None,
        execution_price: Decimal | None,
        broker_deal_id: int | None,
        require_partial: bool = False,
    ) -> ExecutionStatus:
        """Classify a fill only when actual deal evidence is valid."""
        # An order ticket proves that an order exists, not that a deal filled.
        if broker_deal_id is None:
            return ExecutionStatus.UNKNOWN
        if executed_volume is None or execution_price is None:
            return ExecutionStatus.UNKNOWN
        if executed_volume > requested_volume:
            return ExecutionStatus.UNKNOWN
        if executed_volume == requested_volume:
            if require_partial:
                return ExecutionStatus.UNKNOWN
            return ExecutionStatus.SUCCESS
        if executed_volume < requested_volume:
            return ExecutionStatus.PARTIALLY_FILLED
        return ExecutionStatus.UNKNOWN

    @classmethod
    def _normalize_trade_response(
        cls,
        response: dict[str, Any],
        order: ExecutionOrder,
        *,
        pending_order: bool,
    ) -> ExecutionResult:
        """Normalize an MT5 bridge response without inventing fill evidence."""
        broker_order_id = cls._broker_identifier(
            response,
            ("order_id", "order", "ticket"),
        )
        broker_deal_id = cls._broker_identifier(
            response,
            ("deal_id", "deal"),
        )
        broker_position_id = cls._broker_identifier(
            response,
            ("position_id", "position"),
        )
        raw_volume = cls._first_value(
            response,
            ("executed_volume", "volume_executed", "actual_volume", "volume"),
        )
        raw_price = cls._first_value(
            response,
            ("execution_price", "price", "price_open", "deal_price"),
        )
        executed_volume = cls._positive_decimal(raw_volume)
        execution_price = cls._positive_decimal(raw_price)
        # The bridge exposes the MqlTradeResult return code as `state`.
        # Keep `retcode` as a compatibility alias for other bridge versions.
        retcode = cls._optional_int(cls._first_value(response, ("state", "retcode")))
        request_id = cls._optional_int(response.get("request_id"))
        retcode_external = cls._optional_int(response.get("retcode_external"))
        raw_status = response.get("status")
        if raw_status is None and isinstance(response.get("state"), str):
            raw_status = response.get("state")
        status_text = str(raw_status).strip().upper() if raw_status is not None else ""
        # A NOT_SUBMITTED response is accepted only when the bridge explicitly
        # reports that the broker boundary was not crossed.
        if (
            status_text == "NOT_SUBMITTED"
            or response.get("submitted") is False
            or response.get("submission_attempted") is False
        ):
            status = ExecutionStatus.NOT_SUBMITTED
        elif retcode == cls.TRADE_RETCODE_PLACED:
            status = (
                ExecutionStatus.PLACED
                if broker_order_id is not None
                else ExecutionStatus.UNKNOWN
            )
        elif retcode == cls.TRADE_RETCODE_DONE:
            if pending_order:
                # Successful placement of a pending order is not itself a fill.
                status = (
                    ExecutionStatus.PLACED
                    if broker_order_id is not None
                    else ExecutionStatus.UNKNOWN
                )
            else:
                status = cls._confirmed_fill_status(
                    requested_volume=order.volume,
                    executed_volume=executed_volume,
                    execution_price=execution_price,
                    broker_deal_id=broker_deal_id,
                )
        elif retcode == cls.TRADE_RETCODE_DONE_PARTIAL:
            status = cls._confirmed_fill_status(
                requested_volume=order.volume,
                executed_volume=executed_volume,
                execution_price=execution_price,
                broker_deal_id=broker_deal_id,
                require_partial=True,
            )
        elif retcode in cls.TRADE_RETCODES_REJECTED:
            status = ExecutionStatus.REJECTED
        elif retcode is not None:
            # Do not interpret an unknown or transient return code as success.
            status = ExecutionStatus.UNKNOWN
        elif status_text in {"SUCCESS", "FILLED", "DONE", "EXECUTED"}:
            if pending_order:
                status = (
                    ExecutionStatus.PLACED
                    if broker_order_id is not None
                    else ExecutionStatus.UNKNOWN
                )
            else:
                status = cls._confirmed_fill_status(
                    requested_volume=order.volume,
                    executed_volume=executed_volume,
                    execution_price=execution_price,
                    broker_deal_id=broker_deal_id,
                )
        elif status_text in {"PARTIAL", "PARTIALLY_FILLED", "DONE_PARTIAL"}:
            status = cls._confirmed_fill_status(
                requested_volume=order.volume,
                executed_volume=executed_volume,
                execution_price=execution_price,
                broker_deal_id=broker_deal_id,
                require_partial=True,
            )
        elif status_text in {"PLACED", "PENDING", "ACCEPTED"}:
            status = (
                ExecutionStatus.PLACED
                if broker_order_id is not None
                else ExecutionStatus.UNKNOWN
            )
        elif status_text in {"REJECTED", "REJECT", "CANCELLED", "CANCELED"}:
            status = ExecutionStatus.REJECTED
        else:
            # Includes absent status, FAILED, ERROR, and UNKNOWN.
            status = ExecutionStatus.UNKNOWN
        message = (
            response.get("message")
            or response.get("comment")
            or response.get("retcode_description")
        )
        if message is None:
            if retcode is not None:
                message = f"MT5 returned trade retcode {retcode}."
            else:
                message = "MT5 response did not establish a definitive outcome."
        if (
            status in {ExecutionStatus.UNKNOWN, ExecutionStatus.REJECTED}
            and retcode is not None
        ):
            if str(retcode) not in str(message):
                message = f"{message} (MT5 retcode={retcode})"
        is_confirmed_fill = status in {
            ExecutionStatus.SUCCESS,
            ExecutionStatus.PARTIALLY_FILLED,
        }
        return ExecutionResult(
            status=status,
            broker=cls.BROKER_NAME,
            broker_order_id=broker_order_id,
            broker_deal_id=broker_deal_id,
            broker_position_id=broker_position_id,
            symbol=str(response.get("symbol") or order.symbol).strip(),
            requested_volume=order.volume,
            volume=executed_volume if is_confirmed_fill else None,
            price=execution_price if is_confirmed_fill else None,
            retcode=retcode,
            request_id=request_id,
            retcode_external=retcode_external,
            message=str(message),
            raw_response=response,
        )

    # ==========================================================
    # ORDERS

    # ==========================================================

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        if order.order_type == OrderType.MARKET:
            return await self.execute_order(order)
        if order.order_type in (
            OrderType.LIMIT,
            OrderType.STOP,
        ):
            return await self.create_pending_order(order)
        raise BrokerOrderError(f"Unsupported order type: {order.order_type}")

    async def execute_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """Submit a market order and normalize the bridge response."""
        if order.order_type != OrderType.MARKET:
            raise BrokerOrderError("execute_order() only supports MARKET orders.")
        try:
            payload = MT5OrderMapper.to_mt5(order)
            # Use a current executable market price as the request price.
            # This is NOT treated as the eventual execution price.
            if order.price is None:
                tick = await self.get_tick(order.symbol)
                if order.side == OrderSide.BUY:
                    market_price = tick["ask"]
                elif order.side == OrderSide.SELL:
                    market_price = tick["bid"]
                else:
                    raise BrokerOrderError(f"Unsupported order side: {order.side}")
                payload["price"] = float(market_price)
            else:
                if order.price <= 0:
                    raise BrokerOrderError(
                        "Market order price must be greater than zero."
                    )
                payload["price"] = float(order.price)
            data = await self.client.post("/orders", payload)
            if not isinstance(data, dict):
                raise BrokerOrderError(
                    "MT5 Bridge returned an invalid market-order response."
                )
            return self._normalize_trade_response(
                data,
                order,
                pending_order=False,
            )
        except (BrokerOrderError, BrokerDataError):
            raise
        except RuntimeError as exc:
            raise BrokerOrderError(f"MT5 order execution failed: {exc}") from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """Create a pending order and normalize its broker response."""
        if order.order_type not in (OrderType.LIMIT, OrderType.STOP):
            raise BrokerOrderError("Pending order must be LIMIT or STOP.")
        if order.price is None:
            raise BrokerOrderError("Pending order requires a price.")
        try:
            payload = MT5OrderMapper.to_mt5(order)
            data = await self.client.post(
                "/orders/pending",
                payload,
            )
            if not isinstance(data, dict):
                raise BrokerOrderError(
                    "MT5 Bridge returned an invalid pending-order response."
                )
            return self._normalize_trade_response(
                data,
                order,
                pending_order=True,
            )
        except BrokerOrderError:
            raise
        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to create pending MT5 order: {exc}"
            ) from exc

    async def get_orders(self):
        """
        Retrieve currently active/pending broker orders.
        """
        try:
            return await self.client.get("/orders")
        except RuntimeError as exc:
            raise BrokerDataError(f"Failed to retrieve MT5 orders: {exc}") from exc

    # ==========================================================
    # POSITIONS

    # ==========================================================

    async def get_positions(self):
        """
        Retrieve all open MT5 positions.
        """
        try:
            return await self.client.get("/positions")
        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 positions: {exc}"
            ) from exc

    async def get_position(
        self,
        position_id: int,
    ):
        """
        Retrieve a single MT5 position.
        """
        try:
            return await self.client.get(f"/positions/{position_id}")
        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 position {position_id}: {exc}"
            ) from exc

    async def modify_position(
        self,
        position_id: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ):
        """
        Modify SL/TP on an existing position.
        """
        if stop_loss is None and take_profit is None:
            raise BrokerPositionError(
                "At least one of stop_loss or " "take_profit must be provided."
            )
        payload: dict[str, float] = {}
        if stop_loss is not None:
            payload["sl"] = float(stop_loss)
        if take_profit is not None:
            payload["tp"] = float(take_profit)
        try:
            return await self.client.patch(
                f"/positions/{position_id}",
                payload,
            )
        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to modify MT5 position {position_id}: {exc}"
            ) from exc

    async def close_position(
        self,
        position_id: int,
    ):
        """
        Close an existing MT5 position.
        """
        try:
            return await self.client.post(f"/positions/{position_id}/close")
        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to close MT5 position {position_id}: {exc}"
            ) from exc

    # ==========================================================
    # HISTORY

    # ==========================================================

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ):
        """
        Retrieve historical MT5 orders.
        Broker-specific MT5 state values are normalized here
        so consumers never have to understand MT5 numeric enums.
        """
        try:
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
            response = await self.client.get(
                "/history/orders",
                params=params,
            )
            return self._normalize_order_history(response)
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 order history: {exc}"
            ) from exc

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ):
        """
        Retrieve historical MT5 deals.
        """
        try:
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
            return await self.client.get(
                "/history/deals",
                params=params,
            )
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 deal history: {exc}"
            ) from exc

    async def get_deals_by_position(
        self,
        position_id: int,
    ):
        """
        Retrieve deals associated with a position.
        """
        try:
            return await self.client.get(f"/history/deals/position/{position_id}")
        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve deals for position {position_id}: {exc}"
            ) from exc

    # ==========================================================
    # HISTORY NORMALIZATION

    # ==========================================================

    @classmethod
    def _normalize_order_history(
        cls,
        response: Any,
    ) -> list[dict[str, Any]]:
        """
        Normalize MT5 historical order responses.
        The bridge may return either:
            - a raw list of orders
            - {"orders": [...]}
            - {"data": [...]}
        Each order receives:
            state       -> AQE semantic state
            state_raw   -> original MT5 value
        The raw broker value is deliberately preserved for
        diagnostics while the semantic value is used by
        broker-neutral services.
        """
        if response is None:
            return []
        if isinstance(response, dict):
            if isinstance(
                response.get("orders"),
                list,
            ):
                orders = response["orders"]
            elif isinstance(
                response.get("data"),
                list,
            ):
                orders = response["data"]
            else:
                return []
        elif isinstance(response, list):
            orders = response
        else:
            return []
        normalized: list[dict[str, Any]] = []
        for item in orders:
            if not isinstance(item, dict):
                continue
            order = dict(item)
            raw_state = order.get("state")
            order["state_raw"] = raw_state
            order["state"] = cls._normalize_order_state(raw_state)
            normalized.append(order)
        return normalized

    @classmethod
    def _normalize_order_state(
        cls,
        state: Any,
    ) -> str:
        """
        Convert MT5 numeric/string order states into
        broker-neutral semantic states.
        Returned values are intentionally aligned with
        OrderReconciliationService expectations.
        """
        if state is None:
            return "UNKNOWN"
        # ------------------------------------------------------
        # Numeric MT5 state
        # ------------------------------------------------------
        numeric_state: int | None = None
        if isinstance(state, bool):
            numeric_state = None
        elif isinstance(state, int):
            numeric_state = state
        elif isinstance(state, float):
            if state.is_integer():
                numeric_state = int(state)
        elif isinstance(state, str):
            value = state.strip()
            if value.isdigit():
                numeric_state = int(value)
            else:
                normalized = value.upper()
                string_mapping = {
                    "STARTED": "PENDING",
                    "PLACED": "PENDING",
                    "PARTIAL": "PARTIALLY_FILLED",
                    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
                    "FILLED": "FILLED",
                    "REJECTED": "REJECTED",
                    "CANCELED": "CANCELLED",
                    "CANCELLED": "CANCELLED",
                    "EXPIRED": "EXPIRED",
                    "REQUEST_ADD": "PENDING",
                    "REQUEST_MODIFY": "PENDING",
                    "REQUEST_CANCEL": "PENDING",
                    "PENDING": "PENDING",
                    "OPEN": "PENDING",
                    "ACCEPTED": "PENDING",
                }
                return string_mapping.get(
                    normalized,
                    "UNKNOWN",
                )
        # ------------------------------------------------------
        # Numeric mapping
        # ------------------------------------------------------
        numeric_mapping = {
            cls.ORDER_STATE_STARTED: "PENDING",
            cls.ORDER_STATE_PLACED: "PENDING",
            cls.ORDER_STATE_CANCELED: "CANCELLED",
            cls.ORDER_STATE_PARTIAL: "PARTIALLY_FILLED",
            cls.ORDER_STATE_FILLED: "FILLED",
            cls.ORDER_STATE_REJECTED: "REJECTED",
            cls.ORDER_STATE_EXPIRED: "EXPIRED",
            cls.ORDER_STATE_REQUEST_ADD: "PENDING",
            cls.ORDER_STATE_REQUEST_MODIFY: "PENDING",
            cls.ORDER_STATE_REQUEST_CANCEL: "PENDING",
        }
        if numeric_state is not None:
            return numeric_mapping.get(
                numeric_state,
                "UNKNOWN",
            )
        return "UNKNOWN"
