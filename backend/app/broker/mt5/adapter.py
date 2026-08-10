import httpx

from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerOrderError,
    BrokerPositionError,
)
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
)


class MT5Adapter(BrokerAdapter):
    """
    MetaTrader 5 broker adapter.

    AQE communicates with the MT5 Bridge through HTTP.
    The bridge communicates with the actual MetaTrader 5 terminal.
    """

    def __init__(
        self,
        bridge_url: str,
        timeout: float = 10.0,
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self.timeout = timeout

    # ==========================================================
    # CONNECTION
    # ==========================================================

    async def connect(
        self,
        credentials: dict,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    f"{self.bridge_url}/connection/connect",
                    json=credentials,
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"MT5 connection failed: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"MT5 connection failed: {exc}"
            ) from exc

    # ==========================================================
    # DISCONNECT
    # ==========================================================

    async def disconnect(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    f"{self.bridge_url}/connection/disconnect"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"MT5 disconnect failed: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"MT5 disconnect failed: {exc}"
            ) from exc

    # ==========================================================
    # CONNECTION STATUS
    # ==========================================================

    async def get_status(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/connection/status"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 status: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 status: {exc}"
            ) from exc

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def get_account(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/account"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 account: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 account: {exc}"
            ) from exc

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    async def get_symbols(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/symbols"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 symbols: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve MT5 symbols: {exc}"
            ) from exc

    # ==========================================================
    # SINGLE SYMBOL
    # ==========================================================

    async def get_symbol(
        self,
        symbol: str,
    ):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/symbols/{symbol}"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve symbol {symbol}: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve symbol {symbol}: {exc}"
            ) from exc

    # ==========================================================
    # TICK
    # ==========================================================

    async def get_tick(
        self,
        symbol: str,
    ):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/symbols/{symbol}"
                )

                response.raise_for_status()

                data = response.json()

            if "bid" not in data or "ask" not in data:
                raise BrokerConnectionError(
                    f"MT5 bridge did not return bid/ask "
                    f"for {symbol}"
                )

            return {
                "symbol": symbol,
                "bid": data["bid"],
                "ask": data["ask"],
            }

        except httpx.HTTPStatusError as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve tick for {symbol}: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise BrokerConnectionError(
                f"Unable to reach MT5 bridge: {exc}"
            ) from exc

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve tick for {symbol}: {exc}"
            ) from exc
    
    # PLACE ORDER
    # ==========================================================

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:

        try:
            # -------------------------------------------------
            # 1. Get current tick
            # -------------------------------------------------

            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                tick_response = await client.get(
                    f"{self.bridge_url}/symbols/{order.symbol}/tick"
                )

                tick_response.raise_for_status()

                tick = tick_response.json()

                # -------------------------------------------------
                # 2. Determine MT5 order type and execution price
                # -------------------------------------------------

                if order.side == OrderSide.BUY:
                    mt5_order_type = 0
                    execution_price = tick["ask"]

                elif order.side == OrderSide.SELL:
                    mt5_order_type = 1
                    execution_price = tick["bid"]

                else:
                    raise BrokerOrderError(
                        f"Unsupported order side: {order.side}"
                    )

                # -------------------------------------------------
                # 3. Build MT5 bridge request
                # -------------------------------------------------

                payload = {
                    "symbol": order.symbol,
                    "volume": float(order.volume),

                    "order_type": mt5_order_type,

                    "price": (
                        float(order.price)
                        if order.price is not None
                        else float(execution_price)
                    ),

                    "sl": (
                        float(order.stop_loss)
                        if order.stop_loss is not None
                        else None
                    ),

                    "tp": (
                        float(order.take_profit)
                        if order.take_profit is not None
                        else None
                    ),

                    "deviation": order.deviation,

                    "magic": order.magic_number,

                    "comment": order.comment or "AQE",
                }

                # -------------------------------------------------
                # 4. Send order to MT5 bridge
                # -------------------------------------------------

                response = await client.post(
                    f"{self.bridge_url}/orders",
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

            # -------------------------------------------------
            # 5. Convert bridge response to AQE response
            # -------------------------------------------------

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                broker="MT5",

                order_id=data.get("ticket"),

                position_id=None,

                symbol=data.get(
                    "symbol",
                    order.symbol,
                ),

                volume=data.get(
                    "volume",
                    float(order.volume),
                ),

                price=data.get("price_open"),

                message=data.get(
                    "comment",
                    "Order executed successfully",
                ),

                raw_response=data,
            )

        except httpx.HTTPStatusError as exc:

            detail = exc.response.text

            raise BrokerOrderError(
                f"MT5 bridge rejected order: {detail}"
            ) from exc

        except httpx.HTTPError as exc:

            raise BrokerOrderError(
                f"MT5 bridge request failed: {exc}"
            ) from exc

        except BrokerOrderError:

            raise

        except Exception as exc:

            raise BrokerOrderError(
                f"MT5 order execution failed: {exc}"
            ) from exc
    # GET ORDERS
    # ==========================================================

    async def get_orders(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/orders"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:

            raise BrokerOrderError(
                f"Failed to retrieve MT5 orders: {exc}"
            ) from exc

        except Exception as exc:

            raise BrokerOrderError(
                f"Failed to retrieve MT5 orders: {exc}"
            ) from exc

    # ==========================================================
    # GET POSITIONS
    # ==========================================================

    async def get_positions(self):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    f"{self.bridge_url}/positions"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as exc:

            raise BrokerPositionError(
                f"Failed to retrieve MT5 positions: {exc}"
            ) from exc

        except Exception as exc:

            raise BrokerPositionError(
                f"Failed to retrieve MT5 positions: {exc}"
            ) from exc

    # ==========================================================
    # CLOSE POSITION
    # ==========================================================

    async def close_position(
        self,
        position_id: int,
    ):

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    f"{self.bridge_url}/positions/"
                    f"{position_id}/close"
                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPStatusError as exc:

            raise BrokerPositionError(
                f"MT5 rejected position close: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:

            raise BrokerPositionError(
                f"Unable to reach MT5 bridge: "
                f"{exc}"
            ) from exc

        except Exception as exc:

            raise BrokerPositionError(
                f"Failed to close MT5 position "
                f"{position_id}: {exc}"
            ) from exc