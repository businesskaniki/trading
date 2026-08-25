from datetime import datetime

import httpx

from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)

from app.exceptions.broker import (
    BrokerOrderError,
    BrokerPositionError,
)


class MT5Client:
    """
    Low-level HTTP client for the MT5 Bridge.
    """

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self.timeout = timeout

    async def get(
        self,
        endpoint: str,
        params: dict | None = None,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}{endpoint}",
                    params=params,
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MT5 Bridge HTTP error "
                f"{exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Unable to reach MT5 Bridge: {exc}"
            ) from exc

    async def post(
        self,
        endpoint: str,
        data: dict | None = None,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    f"{self.bridge_url}{endpoint}",
                    json=data,
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MT5 Bridge HTTP error "
                f"{exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Unable to reach MT5 Bridge: {exc}"
            ) from exc

    async def patch(
        self,
        endpoint: str,
        data: dict | None = None,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.patch(
                    f"{self.bridge_url}{endpoint}",
                    json=data,
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MT5 Bridge HTTP error "
                f"{exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Unable to reach MT5 Bridge: {exc}"
            ) from exc


class MT5OrderMapper:
    """
    Converts AQE broker-agnostic orders into
    MT5 Bridge order payloads.
    """

    @staticmethod
    def to_mt5(
        order: ExecutionOrder,
    ) -> dict:

        payload = {
            "symbol": order.symbol,
            "volume": float(order.volume),
            "deviation": order.deviation,
            "magic": order.magic_number,
            "comment": (
                str(order.comment).strip()[:31]
                if order.comment
                else "AQE"
            ),
        }

        # ======================================================
        # MARKET
        # ======================================================

        if order.order_type == OrderType.MARKET:

            if order.side == OrderSide.BUY:
                payload["order_type"] = 0

            elif order.side == OrderSide.SELL:
                payload["order_type"] = 1

            else:
                raise BrokerOrderError(
                    f"Unsupported order side: {order.side}"
                )

        # ======================================================
        # LIMIT
        # ======================================================

        elif order.order_type == OrderType.LIMIT:

            if order.side == OrderSide.BUY:
                payload["order_type"] = 2

            elif order.side == OrderSide.SELL:
                payload["order_type"] = 3

            else:
                raise BrokerOrderError(
                    f"Unsupported order side: {order.side}"
                )

            if order.price is None:
                raise BrokerOrderError(
                    "LIMIT order requires a price"
                )

            payload["price"] = float(order.price)

        # ======================================================
        # STOP
        # ======================================================

        elif order.order_type == OrderType.STOP:

            if order.side == OrderSide.BUY:
                payload["order_type"] = 4

            elif order.side == OrderSide.SELL:
                payload["order_type"] = 5

            else:
                raise BrokerOrderError(
                    f"Unsupported order side: {order.side}"
                )

            if order.price is None:
                raise BrokerOrderError(
                    "STOP order requires a price"
                )

            payload["price"] = float(order.price)

        else:
            raise BrokerOrderError(
                f"Unsupported order type: "
                f"{order.order_type}"
            )

        # ======================================================
        # STOP LOSS
        # ======================================================

        if order.stop_loss is not None:
            payload["sl"] = float(
                order.stop_loss
            )

        # ======================================================
        # TAKE PROFIT
        # ======================================================

        if order.take_profit is not None:
            payload["tp"] = float(
                order.take_profit
            )

        return payload


class MT5Adapter:
    """
    AQE broker adapter for MetaTrader 5.
    """

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
    ):
        self.client = MT5Client(
            bridge_url=bridge_url,
            timeout=timeout,
        )

        self.bridge_url = bridge_url.rstrip("/")

    # ==========================================================
    # MARKET ORDER
    # ==========================================================

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ):

        try:

            if order.order_type not in (
                OrderType.LIMIT,
                OrderType.STOP,
            ):
                raise BrokerOrderError(
                    "Pending order must be "
                    "LIMIT or STOP."
                )

            if order.price is None:
                raise BrokerOrderError(
                    "Pending order requires a price."
                )

            payload = MT5OrderMapper.to_mt5(
                order
            )

            return await self.client.post(
                "/orders/pending",
                payload,
            )

        except BrokerOrderError:
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to create pending "
                f"MT5 order: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to create pending "
                f"MT5 order: {exc}"
            ) from exc

    # ==========================================================
    # ORDERS
    # ==========================================================

    async def get_orders(self):

        try:

            return await self.client.get(
                "/orders"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 orders: "
                f"{exc}"
            ) from exc

    # ==========================================================
    # POSITIONS
    # ==========================================================

    async def get_positions(self):

        try:

            return await self.client.get(
                "/positions"
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 positions: "
                f"{exc}"
            ) from exc

    async def get_position(
        self,
        position_id: int,
    ):

        try:

            return await self.client.get(
                f"/positions/{position_id}"
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to retrieve MT5 position "
                f"{position_id}: {exc}"
            ) from exc

    # ==========================================================
    # MODIFY POSITION
    # ==========================================================

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):

        try:

            if (
                sl is None
                and tp is None
            ):
                raise BrokerPositionError(
                    "At least one of stop_loss "
                    "or take_profit must be provided."
                )

            payload = {}

            if sl is not None:
                payload["sl"] = float(
                    sl
                )

            if tp is not None:
                payload["tp"] = float(
                    tp
                )

            return await self.client.patch(
                f"/positions/{position_id}",
                payload,
            )

        except BrokerPositionError:
            raise

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to modify MT5 position "
                f"{position_id}: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to modify MT5 position "
                f"{position_id}: {exc}"
            ) from exc

    # ==========================================================
    # CLOSE POSITION
    # ==========================================================

    async def close_position(
        self,
        position_id: int,
    ):

        try:

            return await self.client.post(
                f"/positions/{position_id}/close"
            )

        except RuntimeError as exc:
            raise BrokerPositionError(
                f"Failed to close MT5 position "
                f"{position_id}: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close MT5 position "
                f"{position_id}: {exc}"
            ) from exc

    # ==========================================================
    # ORDER HISTORY
    # ==========================================================

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ):

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
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"order history: {exc}"
            ) from exc

    # ==========================================================
    # DEAL HISTORY
    # ==========================================================

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ):

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
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"deal history: {exc}"
            ) from exc

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def get_account(self):

        try:

            return await self.client.get(
                "/account"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"account: {exc}"
            ) from exc

    # ==========================================================
    # SYMBOL
    # ==========================================================

    async def get_symbol(
        self,
        symbol: str,
    ):

        try:

            return await self.client.get(
                f"/symbols/{symbol}"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"symbol {symbol}: {exc}"
            ) from exc

    # ==========================================================
    # TICK
    # ==========================================================

    async def get_tick(
        self,
        symbol: str,
    ):

        try:

            return await self.client.get(
                f"/symbols/{symbol}/tick"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"tick for {symbol}: {exc}"
            ) from exc

    # ==========================================================
    # CONNECTION STATUS
    # ==========================================================

    async def connection_status(self):

        try:

            return await self.client.get(
                "/connection/status"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 "
                f"connection status: {exc}"
            ) from exc

    # ==========================================================
    # CONNECT
    # ==========================================================

    async def connect(self):

        try:

            return await self.client.post(
                "/connection/connect"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to connect to MT5: {exc}"
            ) from exc

    # ==========================================================
    # DISCONNECT
    # ==========================================================

    async def disconnect(self):

        try:

            return await self.client.post(
                "/connection/disconnect"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to disconnect from MT5: {exc}"
            ) from exc


    # ==========================================================
# ORDER INTERFACE
# ==========================================================

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Standard broker interface for placing an order.
        """

        if order.order_type == OrderType.MARKET:
            return await self.execute_order(order)

        if order.order_type in (
            OrderType.LIMIT,
            OrderType.STOP,
        ):
            return await self.create_pending_order(order)

        raise BrokerOrderError(
            f"Unsupported order type: {order.order_type}"
        )


    # ==========================================================
    # MARKET ORDER
    # ==========================================================

    async def execute_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:

        try:
            if order.order_type != OrderType.MARKET:
                raise BrokerOrderError(
                    "execute_order() only supports MARKET orders. "
                    "Use create_pending_order() for LIMIT and STOP orders."
                )

            # ------------------------------------------------------
            # Build the broker payload
            # ------------------------------------------------------

            payload = MT5OrderMapper.to_mt5(order)

            # ------------------------------------------------------
            # Resolve executable market price
            # ------------------------------------------------------

            if order.price is None:
                tick = await self.client.get(
                    f"/symbols/{order.symbol}/tick"
                )

                if order.side == OrderSide.BUY:
                    market_price = tick["ask"]
                else:
                    market_price = tick["bid"]

                payload["price"] = float(market_price)

            else:
                payload["price"] = float(order.price)

            # ------------------------------------------------------
            # Send order to MT5 Bridge
            # ------------------------------------------------------

            data = await self.client.post(
                "/orders",
                payload,
            )

            # ------------------------------------------------------
            # Normalize broker response
            # ------------------------------------------------------

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                broker="MT5",
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

        except BrokerOrderError:
            raise

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"MT5 order execution failed: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerOrderError(
                f"MT5 order execution failed: {exc}"
            ) from exc


    async def get_deals_by_position(
        self,
        position_id: int,
    ):
        try:
            return await self.client.get(
                f"/history/deals/position/{position_id}"
            )

        except RuntimeError as exc:
            raise BrokerOrderError(
                f"Failed to retrieve MT5 deals "
                f"for position {position_id}: {exc}"
            ) from exc