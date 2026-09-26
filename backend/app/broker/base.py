from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    """
    Abstract interface for all broker implementations.

    AQE communicates with this interface rather than directly
    communicating with MT5, Paper Trading, or another broker.
    """

    # ==========================================================
    # CONNECTION
    # ==========================================================

    @abstractmethod
    async def connect(self, credentials: dict):
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self):
        raise NotImplementedError

    @abstractmethod
    async def connection_status(self):
        raise NotImplementedError

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    @abstractmethod
    async def get_account(self):
        raise NotImplementedError

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    @abstractmethod
    async def get_symbols(self):
        raise NotImplementedError

    @abstractmethod
    async def get_symbol(self, symbol: str):
        raise NotImplementedError

    @abstractmethod
    async def get_tick(self, symbol: str):
        raise NotImplementedError

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ):
        raise NotImplementedError

    # ==========================================================
    # ORDERS
    # ==========================================================

    @abstractmethod
    async def get_orders(self):
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, order: dict):
        raise NotImplementedError

    @abstractmethod
    async def create_pending_order(self, order: dict):
        raise NotImplementedError

    # ==========================================================
    # POSITIONS
    # ==========================================================

    @abstractmethod
    async def get_positions(self):
        raise NotImplementedError

    @abstractmethod
    async def get_position(self, position_id: int):
        raise NotImplementedError

    @abstractmethod
    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        raise NotImplementedError

    @abstractmethod
    async def close_position(self, position_id: int):
        raise NotImplementedError

    # ==========================================================
    # HISTORY
    # ==========================================================

    @abstractmethod
    async def get_order_history(self, start, end):
        raise NotImplementedError

    @abstractmethod
    async def get_deal_history(self, start, end):
        raise NotImplementedError

    @abstractmethod
    async def get_deals_by_position(self, position_id: int):
        """
        Retrieve broker deals associated with a position.
        """
        raise NotImplementedError
