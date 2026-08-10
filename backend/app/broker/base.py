from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    """
    Abstract interface for all broker implementations.

    The trading engine communicates with this interface
    instead of communicating directly with MT5, Paper Trading,
    or any other broker.
    """

    # ==========================================================
    # Connection
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

    # ==========================================================
    # Account
    # ==========================================================

    @abstractmethod
    async def get_account(self):
        """
        Get the current trading account information.
        """
        raise NotImplementedError

    # ==========================================================
    # Symbols
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

    # ==========================================================
    # Orders
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
        Submit an order to the broker.
        """
        raise NotImplementedError

    # ==========================================================
    # Positions
    # ==========================================================

    @abstractmethod
    async def get_positions(self):
        """
        Get open positions.
        """
        raise NotImplementedError

    @abstractmethod
    async def close_position(self, position_id: int):
        """
        Close an open position.
        """
        raise NotImplementedError