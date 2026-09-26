from __future__ import annotations

from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerOrderError,
    BrokerPositionError,
    BrokerSymbolError,
)
from app.schemas.execution import ExecutionOrder


class BrokerManager:
    """
    High-level broker interface used by the trading engine.

    BrokerManager wraps a single configured BrokerAdapter and provides
    a broker-agnostic interface to the rest of AQE.

    The manager does not contain broker-specific logic. Concrete broker
    behavior remains inside the selected BrokerAdapter implementation.
    """

    def __init__(self, adapter: BrokerAdapter):
        self.adapter = adapter

    # ==========================================================
    # CONNECTION
    # ==========================================================

    async def connect(self, credentials: dict):
        """Connect to the configured broker."""

        try:
            return await self.adapter.connect(credentials)

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(f"Failed to connect to broker: {exc}") from exc

    async def disconnect(self):
        """Disconnect from the configured broker."""

        try:
            return await self.adapter.disconnect()

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to disconnect from broker: {exc}"
            ) from exc

    async def connection_status(self):
        """Return the broker connection status."""

        try:
            return await self.adapter.connection_status()

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve broker connection status: {exc}"
            ) from exc

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def get_account(self):
        """Get broker account information."""

        try:
            return await self.adapter.get_account()

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve broker account: {exc}"
            ) from exc

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    async def get_symbols(self):
        """Get all available broker symbols."""

        try:
            return await self.adapter.get_symbols()

        except BrokerSymbolError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve broker symbols: {exc}"
            ) from exc

    async def get_symbol(self, symbol: str):
        """Get information for a specific symbol."""

        try:
            return await self.adapter.get_symbol(symbol)

        except BrokerSymbolError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve symbol '{symbol}': {exc}"
            ) from exc

    async def get_tick(self, symbol: str):
        """Get the current market tick for a symbol."""

        try:
            return await self.adapter.get_tick(symbol)

        except BrokerSymbolError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve tick for '{symbol}': {exc}"
            ) from exc

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ):
        """
        Get recent OHLC candles for a symbol.

        This is market-data retrieval and is separate from broker
        trading history.
        """

        try:
            return await self.adapter.get_candles(
                symbol,
                timeframe=timeframe,
                count=count,
            )

        except BrokerSymbolError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve candles for '{symbol}': {exc}"
            ) from exc

    # ==========================================================
    # ORDERS
    # ==========================================================

    async def get_orders(self):
        """Get broker orders."""

        try:
            return await self.adapter.get_orders()

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to retrieve broker orders: {exc}") from exc

    async def place_order(
        self,
        order: ExecutionOrder,
    ):
        """
        Submit a normalized execution order to the configured broker.

        ExecutionOrder is the broker-agnostic AQE execution contract.
        Broker-specific translation is handled by the adapter.
        """

        try:
            return await self.adapter.place_order(order)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to place order: {exc}") from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ):
        """
        Submit a pending order directly to the configured broker.

        This method remains available for broker-level operations.
        The ExecutionEngine should normally use place_order(), allowing
        the adapter to determine the broker-specific execution path
        from ExecutionOrder.order_type.
        """

        try:
            return await self.adapter.create_pending_order(order)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to create pending order: {exc}") from exc

    # ==========================================================
    # POSITIONS
    # ==========================================================

    async def get_positions(self):
        """Get open broker positions."""

        try:
            return await self.adapter.get_positions()

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(f"Failed to retrieve positions: {exc}") from exc

    async def get_position(self, position_id: int):
        """Get a single open broker position."""

        try:
            return await self.adapter.get_position(position_id)

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve position {position_id}: {exc}"
            ) from exc

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """Modify the SL/TP of an existing position."""

        try:
            return await self.adapter.modify_position(
                position_id=position_id,
                sl=sl,
                tp=tp,
            )

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to modify position {position_id}: {exc}"
            ) from exc

    async def close_position(self, position_id: int):
        """Close an existing broker position."""

        try:
            return await self.adapter.close_position(position_id)

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close position {position_id}: {exc}"
            ) from exc

    # ==========================================================
    # HISTORY
    # ==========================================================

    async def get_order_history(self, start, end):
        """Retrieve historical broker orders."""

        try:
            return await self.adapter.get_order_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to retrieve order history: {exc}") from exc

    async def get_deal_history(self, start, end):
        """Retrieve historical broker deals."""

        try:
            return await self.adapter.get_deal_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to retrieve broker deals: {exc}") from exc

    async def get_deals_by_position(self, position_id: int):
        """
        Retrieve broker deals associated with a specific position.
        """

        try:
            return await self.adapter.get_deals_by_position(position_id)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve deals for position " f"{position_id}: {exc}"
            ) from exc
