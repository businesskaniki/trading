from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    """
    Abstract interface for all broker implementations.

    AQE communicates with this interface rather than
    directly communicating with MT5, Paper Trading,
    or another broker.
    """

    # ==========================================================
    # CONNECTION
    # ==========================================================

    @abstractmethod
    async def connect(self, credentials: dict):
        """
        Connect to the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self):
        """
        Disconnect from the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def connection_status(self):
        """
        Return the current broker connection status.
        """
        raise NotImplementedError

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    @abstractmethod
    async def get_account(self):
        """
        Get current broker account information.
        """
        raise NotImplementedError

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    @abstractmethod
    async def get_symbols(self):
        """
        Get available trading symbols.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_symbol(self, symbol: str):
        """
        Get information about a specific symbol.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_tick(self, symbol: str):
        """
        Get the latest market tick for a symbol.
        """
        raise NotImplementedError

    # ==========================================================
    # ORDERS
    # ==========================================================

    @abstractmethod
    async def get_orders(self):
        """
        Get current/pending orders from the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, order: dict):
        """
        Submit a market or standard order to the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_pending_order(self, order: dict):
        """
        Create a pending order.
        """
        raise NotImplementedError

    # ==========================================================
    # POSITIONS
    # ==========================================================

    @abstractmethod
    async def get_positions(self):
        """
        Get all open positions.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_position(self, position_id: int):
        """
        Get a specific open position.
        """
        raise NotImplementedError

    @abstractmethod
    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """
        Modify an existing position's stop loss
        and/or take profit.
        """
        raise NotImplementedError

    @abstractmethod
    async def close_position(self, position_id: int):
        """
        Close an open position.
        """
        raise NotImplementedError

    # ==========================================================
    # HISTORY
    # ==========================================================

    @abstractmethod
    async def get_order_history(
        self,
        start,
        end,
    ):
        """
        Get historical orders within a time range.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_deal_history(
        self,
        start,
        end,
    ):
        """
        Get historical deals within a time range.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_tick(self, symbol: str):
        raise NotImplementedError