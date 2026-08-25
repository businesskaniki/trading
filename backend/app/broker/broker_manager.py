from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerOrderError,
    BrokerPositionError,
    BrokerSymbolError,
)


class BrokerManager:
    """
    High-level broker interface used by the trading engine.

    The manager hides the concrete broker implementation
    from the rest of the application.
    """

    def __init__(self, adapter: BrokerAdapter):
        self.adapter = adapter

    # ==========================================================
    # Connection
    # ==========================================================

    async def connect(self, credentials: dict):
        """
        Connect to the configured broker.
        """

        try:
            return await self.adapter.connect(credentials)

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to connect to broker: {exc}"
            ) from exc

    async def disconnect(self):
        """
        Disconnect from the configured broker.
        """

        try:
            return await self.adapter.disconnect()

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to disconnect from broker: {exc}"
            ) from exc

    # ==========================================================
    # Account
    # ==========================================================

    async def get_account(self):
        """
        Get broker account information.
        """

        try:
            return await self.adapter.get_account()

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve broker account: {exc}"
            ) from exc

    # ==========================================================
    # Symbols
    # ==========================================================

    async def get_symbols(self):
        """
        Get all available broker symbols.
        """

        try:
            return await self.adapter.get_symbols()

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve broker symbols: {exc}"
            ) from exc

    async def get_symbol(self, symbol: str):
        """
        Get information for a specific symbol.
        """

        try:
            return await self.adapter.get_symbol(symbol)

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve symbol '{symbol}': {exc}"
            ) from exc

    # ==========================================================
    # Orders
    # ==========================================================

    async def get_orders(self):
        """
        Get broker orders.
        """

        try:
            return await self.adapter.get_orders()

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve broker orders: {exc}"
            ) from exc

    async def place_order(self, order: dict):
        """
        Submit an order to the broker.
        """

        try:
            return await self.adapter.place_order(order)

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to place order: {exc}"
            ) from exc

    # ==========================================================
    # Positions
    # ==========================================================

    async def get_positions(self):
        """
        Get open broker positions.
        """

        try:
            return await self.adapter.get_positions()

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve positions: {exc}"
            ) from exc

    async def close_position(self, position_id: int):
        """
        Close a broker position.
        """

        try:
            return await self.adapter.close_position(
                position_id
            )

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close position "
                f"{position_id}: {exc}"
            ) from exc


    # ==========================================================
# PENDING ORDERS
# ==========================================================

    async def create_pending_order(self, order: dict):
        """
        Submit a pending order to the broker.
        """

        try:
            return await self.adapter.create_pending_order(order)

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to create pending order: {exc}"
            ) from exc


    # ==========================================================
    # POSITION
    # ==========================================================

    async def get_position(self, position_id: int):
        """
        Get a single open position.
        """

        try:
            return await self.adapter.get_position(position_id)

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve position "
                f"{position_id}: {exc}"
            ) from exc


    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """
        Modify the SL/TP of an existing position.
        """

        try:
            return await self.adapter.modify_position(
                position_id=position_id,
                sl=sl,
                tp=tp,
            )

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to modify position "
                f"{position_id}: {exc}"
            ) from exc


    # ==========================================================
    # HISTORY
    # ==========================================================

    async def get_order_history(
        self,
        start,
        end,
    ):
        """
        Retrieve historical orders.
        """

        try:
            return await self.adapter.get_order_history(
                start=start,
                end=end,
            )

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve order history: {exc}"
            ) from exc


    async def get_deal_history(
        self,
        start,
        end,
    ):
        """
        Retrieve historical deals.
        """

        try:
            return await self.adapter.get_deal_history(
                start=start,
                end=end,
            )

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve deal history: {exc}"
            ) from exc


    async def get_tick(self, symbol: str):
        """
        Get the current market tick for a symbol.
        """

        try:
            return await self.adapter.get_tick(symbol)

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve tick for '{symbol}': {exc}"
            ) from exc

    async def get_deals_by_position(
        self,
        position_id: int,
    ):
        """
        Retrieve broker deal history for a specific position.
        """

        try:
            return await self.adapter.get_deals_by_position(
                position_id
            )

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve deals for position "
                f"{position_id}: {exc}"
            ) from exc