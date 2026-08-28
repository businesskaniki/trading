from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class Broker(ABC):
    """
    Abstract broker interface used by the trading engine.

    Concrete implementations such as MT5Broker and PaperBroker
    must implement this interface.

    The engine depends on this contract rather than depending
    directly on MetaTrader 5 or any other broker.
    """

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish a connection to the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close the broker connection and release resources.
        """
        raise NotImplementedError

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Return True when the broker connection is healthy.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_account(self) -> dict[str, Any]:
        """
        Return current broker account information.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_balance(self) -> Decimal:
        """
        Return current account balance.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_equity(self) -> Decimal:
        """
        Return current account equity.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_symbol(self, symbol: str) -> dict[str, Any]:
        """
        Return broker information for a symbol.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_tick(self, symbol: str) -> dict[str, Any]:
        """
        Return the latest bid/ask tick for a symbol.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    @abstractmethod
    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        volume: Decimal,
        order_type: str,
        price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        comment: str | None = None,
        magic_number: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Submit an order to the broker.
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an existing pending order.
        """
        raise NotImplementedError

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        *,
        price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Modify an existing order.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return currently open positions.

        If symbol is supplied, return positions for that symbol only.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_position(
        self,
        position_id: str,
    ) -> dict[str, Any] | None:
        """
        Return a single open position.
        """
        raise NotImplementedError

    @abstractmethod
    async def close_position(
        self,
        position_id: str,
        *,
        volume: Decimal | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Close all or part of an open position.
        """
        raise NotImplementedError

    @abstractmethod
    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Modify the protective levels of an open position.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_orders(
        self,
        *,
        start: Any | None = None,
        end: Any | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return historical broker orders.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_trades(
        self,
        *,
        start: Any | None = None,
        end: Any | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return historical executed trades/deals.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Return broker health/status information.
        """
        raise NotImplementedError
