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
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)
from app.core.config import settings

from .client import MT5Client


class MT5OrderMapper:
    """
    Converts AQE broker-agnostic ExecutionOrder objects
    into MT5 Bridge order payloads.
    """

    MARKET_BUY = 0
    MARKET_SELL = 1

    BUY_LIMIT = 2
    SELL_LIMIT = 3

    BUY_STOP = 4
    SELL_STOP = 5

    @staticmethod
    def to_mt5(order: ExecutionOrder) -> dict[str, Any]:

        if order.volume <= 0:
            raise BrokerOrderError("Order volume must be greater than zero.")

        payload: dict[str, Any] = {
            "symbol": order.symbol,
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

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
        account_id: str | None = None,
    ):
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
                f"Failed to retrieve MT5 symbol " f"{symbol}: {exc}"
            ) from exc

    async def get_tick(
        self,
        symbol: str,
    ):
        """
        Retrieve the latest broker tick.

        This is intentionally separate from order execution
        so market data can also be consumed by the market-data
        layer.
        """

        if not symbol:
            raise BrokerDataError("Symbol cannot be empty.")

        try:
            return await self.client.get(f"/symbols/{symbol}/tick")

        except RuntimeError as exc:
            raise BrokerDataError(
                f"Failed to retrieve tick for " f"{symbol}: {exc}"
            ) from exc

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ):
        """
        Retrieve recent OHLC candles for a symbol.

        Used by the market-data layer to build the price history a
        strategy needs (e.g. EMA calculations) - separate from
        get_tick(), which only returns the current price.
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
                f"Failed to retrieve candles for " f"{symbol}: {exc}"
            ) from exc

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
        """
        Execute a MARKET order.
        """

        if order.order_type != OrderType.MARKET:
            raise BrokerOrderError("execute_order() only supports MARKET orders.")

        try:

            payload = MT5OrderMapper.to_mt5(order)

            # --------------------------------------------------
            # Resolve market price
            # --------------------------------------------------

            if order.price is None:

                tick = await self.get_tick(order.symbol)

                if not tick:
                    raise BrokerDataError(
                        f"No tick data available for " f"{order.symbol}"
                    )

                if order.side == OrderSide.BUY:
                    market_price = tick.get("ask")

                elif order.side == OrderSide.SELL:
                    market_price = tick.get("bid")

                else:
                    raise BrokerOrderError(f"Unsupported order side: {order.side}")

                if market_price is None:
                    raise BrokerDataError(
                        f"Tick for {order.symbol} does not "
                        f"contain the required market price."
                    )

                payload["price"] = float(market_price)

            else:
                payload["price"] = float(order.price)

            # --------------------------------------------------
            # Send order to MT5
            # --------------------------------------------------

            data = await self.client.post(
                "/orders",
                payload,
            )

            # --------------------------------------------------
            # Normalize broker response
            # --------------------------------------------------

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                broker=self.BROKER_NAME,
                order_id=data.get("ticket"),
                position_id=data.get("position_id"),
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
                    payload.get("price"),
                ),
                message=data.get(
                    "comment",
                    "Order executed successfully",
                ),
                raw_response=data,
            )

        except (
            BrokerOrderError,
            BrokerDataError,
        ):
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(f"MT5 order execution failed: {exc}") from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ):
        """
        Create a LIMIT or STOP pending order.
        """

        if order.order_type not in (
            OrderType.LIMIT,
            OrderType.STOP,
        ):
            raise BrokerOrderError("Pending order must be LIMIT or STOP.")

        if order.price is None:
            raise BrokerOrderError("Pending order requires a price.")

        try:

            payload = MT5OrderMapper.to_mt5(order)

            return await self.client.post(
                "/orders/pending",
                payload,
            )

        except BrokerOrderError:
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to create pending MT5 " f"order: {exc}"
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
                f"Failed to retrieve MT5 position " f"{position_id}: {exc}"
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
                f"Failed to modify MT5 position " f"{position_id}: {exc}"
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
                f"Failed to close MT5 position " f"{position_id}: {exc}"
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
                f"Failed to retrieve MT5 " f"order history: {exc}"
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
                f"Failed to retrieve MT5 " f"deal history: {exc}"
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
                f"Failed to retrieve deals for " f"position {position_id}: {exc}"
            ) from exc