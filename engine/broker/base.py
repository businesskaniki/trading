"""Broker abstraction for the Athena Quant Engine.

This module defines the interface that all broker implementations must
follow.

The trading engine depends on this abstraction rather than directly
depending on MetaTrader 5 or another broker SDK.

Concrete implementations may include:

    - MT5Broker
    - PaperBroker
    - Future broker/exchange adapters

The interface intentionally contains no broker-specific implementation
logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from engine.broker.models import (
    AccountInfo,
    Candle,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Position,
    SymbolInfo,
    Tick,
)


class Broker(ABC):
    """Abstract interface for broker connectivity and trading."""

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection to the broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the broker connection."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Return whether the broker connection is active."""

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Return current broker account information."""

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_symbol(self, symbol: str) -> SymbolInfo:
        """Return information about a trading symbol."""

    @abstractmethod
    async def get_tick(self, symbol: str) -> Tick:
        """Return the latest tick for a symbol."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> Sequence[Candle]:
        """Return historical candles for a symbol."""

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    @abstractmethod
    async def submit_order(
        self,
        request: OrderRequest,
    ) -> OrderResult:
        """Submit an order to the broker."""

    @abstractmethod
    async def cancel_order(
        self,
        order_id: str,
    ) -> OrderResult:
        """Cancel an existing order."""

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        *,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Modify an existing order."""

    @abstractmethod
    async def get_order_status(
        self,
        order_id: str,
    ) -> OrderStatus:
        """Return the current status of an order."""

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_positions(
        self,
        symbol: str | None = None,
    ) -> Sequence[Position]:
        """Return currently open positions."""

    @abstractmethod
    async def get_position(
        self,
        position_id: str,
    ) -> Position | None:
        """Return one position by identifier."""

    @abstractmethod
    async def close_position(
        self,
        position_id: str,
    ) -> OrderResult:
        """Close an open position."""

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return broker health information.

        Concrete brokers can override this method when they need to
        expose additional diagnostics.
        """

        connected = await self.is_connected()

        return {
            "status": "healthy" if connected else "disconnected",
            "connected": connected,
            "broker": self.__class__.__name__,
        }


__all__ = [
    "Broker",
]
