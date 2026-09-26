from __future__ import annotations

from datetime import datetime
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
    Converts AQE broker-agnostic ExecutionOrder objects
    into the payload expected by the MT5 Bridge.

    The Bridge API intentionally receives MT5-native order
    type integers.
    """

    # MT5 market order types
    MARKET_BUY = 0
    MARKET_SELL = 1

    # MT5 pending order types
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5

    @classmethod
    def to_mt5(
        cls,
        order: ExecutionOrder,
    ) -> dict[str, Any]:
        """
        Convert an ExecutionOrder into an MT5 Bridge request.
        """

        if order.volume <= 0:
            raise BrokerOrderError(
                "Order volume must be greater than zero.",
            )

        payload: dict[str, Any] = {
            "symbol": order.symbol,
            "volume": float(order.volume),
            "deviation": order.deviation,
            "magic": order.magic_number,
            "comment": (str(order.comment).strip()[:31] if order.comment else "AQE"),
        }

        # ======================================================
        # MARKET ORDERS
        # ======================================================

        if order.order_type == OrderType.MARKET:

            if order.side == OrderSide.BUY:
                payload["order_type"] = cls.MARKET_BUY

            elif order.side == OrderSide.SELL:
                payload["order_type"] = cls.MARKET_SELL

            else:
                raise BrokerOrderError(
                    f"Unsupported market order side: {order.side}",
                )

        # ======================================================
        # LIMIT ORDERS
        # ======================================================

        elif order.order_type == OrderType.LIMIT:

            if order.price is None:
                raise BrokerOrderError(
                    "LIMIT order requires a price.",
                )

            if order.side == OrderSide.BUY:
                payload["order_type"] = cls.BUY_LIMIT

            elif order.side == OrderSide.SELL:
                payload["order_type"] = cls.SELL_LIMIT

            else:
                raise BrokerOrderError(
                    f"Unsupported limit order side: {order.side}",
                )

            payload["price"] = float(order.price)

        # ======================================================
        # STOP ORDERS
        # ======================================================

        elif order.order_type == OrderType.STOP:

            if order.price is None:
                raise BrokerOrderError(
                    "STOP order requires a price.",
                )

            if order.side == OrderSide.BUY:
                payload["order_type"] = cls.BUY_STOP

            elif order.side == OrderSide.SELL:
                payload["order_type"] = cls.SELL_STOP

            else:
                raise BrokerOrderError(
                    f"Unsupported stop order side: {order.side}",
                )

            payload["price"] = float(order.price)

        else:
            raise BrokerOrderError(
                f"Unsupported order type: {order.order_type}",
            )

        # ======================================================
        # STOP LOSS
        # ======================================================

        if order.stop_loss is not None:
            payload["sl"] = float(order.stop_loss)

        # ======================================================
        # TAKE PROFIT
        # ======================================================

        if order.take_profit is not None:
            payload["tp"] = float(order.take_profit)

        return payload


class MT5Adapter(BrokerAdapter):
    """
    AQE MetaTrader 5 broker adapter.

    Responsibilities:
        - Communicate with the MT5 Bridge.
        - Translate AQE orders into MT5 Bridge requests.
        - Normalize MT5 Bridge responses into AQE contracts.
        - Expose MT5 operations through BrokerAdapter.

    This adapter does NOT:
        - Create database records.
        - Run strategies.
        - Perform risk calculations.
        - Generate trading signals.
        - Manage user authentication.
    """

    BROKER_NAME = "MT5"

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
    # INTERNAL HELPERS
    # ==========================================================

    @staticmethod
    def _coerce_execution_order(
        order: ExecutionOrder | dict[str, Any],
    ) -> ExecutionOrder:
        """
        Normalize a broker-layer order into ExecutionOrder.

        BrokerManager/BrokerAdapter historically pass dictionaries,
        while internal execution code may pass ExecutionOrder objects.
        Supporting both keeps the adapter boundary stable.
        """

        if isinstance(order, ExecutionOrder):
            return order

        if not isinstance(order, dict):
            raise BrokerOrderError(
                "Order must be an ExecutionOrder or dictionary.",
            )

        try:
            return ExecutionOrder.model_validate(order)

        except Exception as exc:
            raise BrokerOrderError(
                f"Invalid execution order: {exc}",
            ) from exc

    @staticmethod
    def _normalize_execution_result(
        data: dict[str, Any],
        *,
        order: ExecutionOrder,
        default_message: str,
    ) -> ExecutionResult:
        """
        Convert an MT5 Bridge order response into the AQE
        ExecutionResult contract.

        Bridge identifiers:
            order_id
            deal_id
            position_id

        AQE identifiers:
            broker_order_id
            broker_deal_id
            broker_position_id
        """

        if not isinstance(data, dict):
            raise BrokerOrderError(
                "MT5 Bridge returned an invalid order response.",
            )

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker=MT5Adapter.BROKER_NAME,
            broker_order_id=data.get("order_id"),
            broker_deal_id=data.get("deal_id"),
            broker_position_id=data.get("position_id"),
            symbol=data.get(
                "symbol",
                order.symbol,
            ),
            volume=data.get(
                "volume",
                float(order.volume),
            ),
            price=data.get(
                "price_open",
                data.get("price"),
                order.price,
            ),
            message=data.get(
                "comment",
                default_message,
            ),
            raw_response=data,
        )

    # ==========================================================
    # CONNECTION
    # ==========================================================

    async def connect(
        self,
        credentials: dict[str, Any] | None = None,
    ):
        """
        Connect the MT5 Bridge to the requested MT5 account.

        Credentials are supplied at runtime and are not read
        from the MT5 Bridge environment configuration.
        """

        try:
            return await self.client.post(
                "/connection/connect",
                credentials or {},
            )

        except RuntimeError as exc:
            raise BrokerConnectionError(
                f"Failed to connect to MT5: {exc}",
            ) from exc

    async def disconnect(self):
        """
        Disconnect the MT5 Bridge from the current account.
        """

        try:
            return await self.client.post(
                "/connection/disconnect",
            )

        except RuntimeError as exc:
            raise BrokerConnectionError(
                f"Failed to disconnect from MT5: {exc}",
            ) from exc

    async def connection_status(self):
        """
        Return current MT5 Bridge connection status.
        """

        try:
            return await self.client.get(
                "/connection/status",
            )

        except RuntimeError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 connection status: {exc}",
            ) from exc

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def get_account(self):
        """
        Retrieve account information from MT5.
        """

        try:
            return await self.client.get(
                "/account",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 account: {exc}",
            ) from exc

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    async def get_symbols(self):
        """
        Retrieve available MT5 symbols.
        """

        try:
            return await self.client.get(
                "/symbols",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 symbols: {exc}",
            ) from exc

    async def get_symbol(
        self,
        symbol: str,
    ):
        """
        Retrieve metadata for a single MT5 symbol.
        """

        if not symbol:
            raise BrokerDataError(
                "Symbol cannot be empty.",
            )

        try:
            return await self.client.get(
                f"/symbols/{symbol}",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 symbol {symbol}: {exc}",
            ) from exc

    async def get_tick(
        self,
        symbol: str,
    ):
        """
        Retrieve the latest broker tick.
        """

        if not symbol:
            raise BrokerDataError(
                "Symbol cannot be empty.",
            )

        try:
            return await self.client.get(
                f"/symbols/{symbol}/tick",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve tick for {symbol}: {exc}",
            ) from exc

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
            raise BrokerDataError(
                "Symbol cannot be empty.",
            )

        if count <= 0:
            raise BrokerDataError(
                "Candle count must be greater than zero.",
            )

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
                f"Failed to retrieve candles for {symbol}: {exc}",
            ) from exc

    # ==========================================================
    # ORDERS
    # ==========================================================

    async def place_order(
        self,
        order: ExecutionOrder | dict[str, Any],
    ) -> ExecutionResult:
        """
        Place an AQE order through the MT5 Bridge.
        """

        execution_order = self._coerce_execution_order(
            order,
        )

        if execution_order.order_type == OrderType.MARKET:
            return await self.execute_order(
                execution_order,
            )

        if execution_order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            return await self.create_pending_order(
                execution_order,
            )

        raise BrokerOrderError(
            f"Unsupported order type: {execution_order.order_type}",
        )

    async def execute_order(
        self,
        order: ExecutionOrder | dict[str, Any],
    ) -> ExecutionResult:
        """
        Execute a MARKET order.
        """

        execution_order = self._coerce_execution_order(
            order,
        )

        if execution_order.order_type != OrderType.MARKET:
            raise BrokerOrderError(
                "execute_order() only supports MARKET orders.",
            )

        try:
            payload = MT5OrderMapper.to_mt5(
                execution_order,
            )

            # --------------------------------------------------
            # Resolve market price
            # --------------------------------------------------

            if execution_order.price is None:
                tick = await self.get_tick(
                    execution_order.symbol,
                )

                if not tick:
                    raise BrokerDataError(
                        f"No tick data available for " f"{execution_order.symbol}",
                    )

                if execution_order.side == OrderSide.BUY:
                    market_price = tick.get("ask")

                elif execution_order.side == OrderSide.SELL:
                    market_price = tick.get("bid")

                else:
                    raise BrokerOrderError(
                        f"Unsupported order side: " f"{execution_order.side}",
                    )

                if market_price is None:
                    raise BrokerDataError(
                        f"Tick for {execution_order.symbol} "
                        "does not contain the required market price.",
                    )

                payload["price"] = float(
                    market_price,
                )

            else:
                payload["price"] = float(
                    execution_order.price,
                )

            # --------------------------------------------------
            # Send to MT5 Bridge
            # --------------------------------------------------

            data = await self.client.post(
                "/orders",
                payload,
            )

            return self._normalize_execution_result(
                data,
                order=execution_order,
                default_message="Order executed successfully.",
            )

        except (
            BrokerOrderError,
            BrokerDataError,
        ):
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"MT5 order execution failed: {exc}",
            ) from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder | dict[str, Any],
    ) -> ExecutionResult:
        """
        Create a LIMIT or STOP pending order.
        """

        execution_order = self._coerce_execution_order(
            order,
        )

        if execution_order.order_type not in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise BrokerOrderError(
                "Pending order must be LIMIT or STOP.",
            )

        if execution_order.price is None:
            raise BrokerOrderError(
                "Pending order requires a price.",
            )

        try:
            payload = MT5OrderMapper.to_mt5(
                execution_order,
            )

            data = await self.client.post(
                "/orders/pending",
                payload,
            )

            return self._normalize_execution_result(
                data,
                order=execution_order,
                default_message="Pending order created successfully.",
            )

        except BrokerOrderError:
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to create pending MT5 order: {exc}",
            ) from exc

    async def get_orders(self):
        """
        Retrieve currently active/pending broker orders.
        """

        try:
            return await self.client.get(
                "/orders",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 orders: {exc}",
            ) from exc

    # ==========================================================
    # POSITIONS
    # ==========================================================

    async def get_positions(self):
        """
        Retrieve all open MT5 positions.
        """

        try:
            return await self.client.get(
                "/positions",
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 positions: {exc}",
            ) from exc

    async def get_position(
        self,
        position_id: int,
    ):
        """
        Retrieve a single MT5 position.
        """

        try:
            return await self.client.get(
                f"/positions/{position_id}",
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 position {position_id}: {exc}",
            ) from exc

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """
        Modify SL/TP on an existing MT5 position.

        The parameter names intentionally match BrokerAdapter:
            sl
            tp
        """

        if sl is None and tp is None:
            raise BrokerPositionError(
                "At least one of sl or tp must be provided.",
            )

        payload: dict[str, float] = {}

        if sl is not None:
            payload["sl"] = float(sl)

        if tp is not None:
            payload["tp"] = float(tp)

        try:
            return await self.client.patch(
                f"/positions/{position_id}",
                payload,
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to modify MT5 position " f"{position_id}: {exc}",
            ) from exc

    async def close_position(
        self,
        position_id: int,
    ):
        """
        Close an existing MT5 position.
        """

        try:
            return await self.client.post(
                f"/positions/{position_id}/close",
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to close MT5 position " f"{position_id}: {exc}",
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
        """

        try:
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }

            return await self.client.get(
                "/history/orders",
                params=params,
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve MT5 order history: {exc}",
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
                f"Failed to retrieve MT5 deal history: {exc}",
            ) from exc

    async def get_deals_by_position(
        self,
        position_id: int,
    ):
        """
        Retrieve deals associated with an MT5 position.
        """

        try:
            return await self.client.get(
                f"/history/deals/position/{position_id}",
            )

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve deals for " f"position {position_id}: {exc}",
            ) from exc
