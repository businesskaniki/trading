from __future__ import annotations

from datetime import datetime
from typing import Any

from app.broker.base import BrokerAdapter
from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerDataError,
    BrokerOrderError,
    BrokerPositionError,
    BrokerSymbolError,
)
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
)


class BrokerManager:
    """
    High-level broker interface used by AQE.

    BrokerManager wraps the configured BrokerAdapter and provides a
    broker-agnostic interface to the rest of the system.

    Responsibilities:
        - expose a stable broker interface;
        - delegate broker operations to the configured adapter;
        - normalize unexpected adapter failures into AQE broker
          exceptions.

    BrokerManager does NOT:
        - contain MT5-specific logic;
        - map order types;
        - interpret broker retcodes;
        - perform risk evaluation;
        - generate signals;
        - persist AQE orders;
        - manage strategies;
        - decide whether an order is permitted.

    Concrete broker behavior remains inside BrokerAdapter
    implementations.
    """

    def __init__(
        self,
        adapter: BrokerAdapter,
    ) -> None:
        self.adapter = adapter

    # ==================================================================
    # CONNECTION
    # ==================================================================

    async def connect(
        self,
        credentials: dict[str, Any] | None = None,
    ) -> Any:
        """
        Connect to the configured broker.

        Credentials are passed through to the selected adapter.
        """

        try:
            return await self.adapter.connect(credentials)

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to connect to broker: {exc}",
            ) from exc

    async def disconnect(self) -> Any:
        """
        Disconnect from the configured broker.
        """

        try:
            return await self.adapter.disconnect()

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to disconnect from broker: {exc}",
            ) from exc

    async def connection_status(self) -> Any:
        """
        Return the current broker connection status.
        """

        try:
            return await self.adapter.connection_status()

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerConnectionError(
                f"Failed to retrieve broker connection status: {exc}",
            ) from exc

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    async def get_account(self) -> Any:
        """
        Retrieve broker account information.
        """

        try:
            return await self.adapter.get_account()

        except BrokerDataError:
            raise

        except BrokerConnectionError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve broker account: {exc}",
            ) from exc

    # ==================================================================
    # SYMBOLS / MARKET DATA
    # ==================================================================

    async def get_symbols(self) -> Any:
        """
        Retrieve all available broker symbols.
        """

        try:
            return await self.adapter.get_symbols()

        except BrokerSymbolError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve broker symbols: {exc}",
            ) from exc

    async def get_symbol(
        self,
        symbol: str,
    ) -> Any:
        """
        Retrieve information for a specific broker symbol.
        """

        try:
            return await self.adapter.get_symbol(symbol)

        except BrokerSymbolError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerSymbolError(
                f"Failed to retrieve symbol '{symbol}': {exc}",
            ) from exc

    async def get_tick(
        self,
        symbol: str,
    ) -> Any:
        """
        Retrieve the current market tick for a symbol.
        """

        try:
            return await self.adapter.get_tick(symbol)

        except BrokerSymbolError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve tick for '{symbol}': {exc}",
            ) from exc

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ) -> Any:
        """
        Retrieve recent OHLC candles for a symbol.

        Market-data retrieval is deliberately separate from broker
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

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve candles for '{symbol}': {exc}",
            ) from exc

    # ==================================================================
    # ORDERS
    # ==================================================================

    async def get_orders(self) -> Any:
        """
        Retrieve currently active/pending broker orders.
        """

        try:
            return await self.adapter.get_orders()

        except BrokerOrderError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve broker orders: {exc}",
            ) from exc

    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Submit a normalized AQE execution order to the configured
        broker.

        ExecutionOrder is broker-agnostic.

        The selected BrokerAdapter is responsible for translating
        the order into its native broker representation and returning
        an ExecutionResult.
        """

        try:
            return await self.adapter.place_order(order)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to place order: {exc}",
            ) from exc

    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Submit a pending order directly to the configured broker.

        The normal ExecutionEngine path should generally use
        place_order(), allowing the adapter to dispatch based on
        ExecutionOrder.order_type.
        """

        try:
            return await self.adapter.create_pending_order(order)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to create pending order: {exc}",
            ) from exc

    # ==================================================================
    # POSITIONS
    # ==================================================================

    async def get_positions(self) -> Any:
        """
        Retrieve all open broker positions.
        """

        try:
            return await self.adapter.get_positions()

        except BrokerPositionError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve positions: {exc}",
            ) from exc

    async def get_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Retrieve a single open broker position.
        """

        try:
            return await self.adapter.get_position(position_id)

        except BrokerPositionError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve position {position_id}: {exc}",
            ) from exc

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Any:
        """
        Modify the SL/TP of an existing broker position.
        """

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
                f"Failed to modify position {position_id}: {exc}",
            ) from exc

    async def close_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Close an existing broker position.
        """

        try:
            return await self.adapter.close_position(position_id)

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close position {position_id}: {exc}",
            ) from exc

    # ==================================================================
    # HISTORY
    # ==================================================================

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ) -> Any:
        """
        Retrieve historical broker orders.
        """

        try:
            return await self.adapter.get_order_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve order history: {exc}",
            ) from exc

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ) -> Any:
        """
        Retrieve historical broker deals.
        """

        try:
            return await self.adapter.get_deal_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve broker deals: {exc}",
            ) from exc

    async def get_deals_by_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Retrieve broker deals associated with a position.
        """

        try:
            return await self.adapter.get_deals_by_position(
                position_id,
            )

        except BrokerOrderError:
            raise

        except BrokerDataError:
            raise

        except Exception as exc:
            raise BrokerDataError(
                f"Failed to retrieve deals for position " f"{position_id}: {exc}",
            ) from exc
