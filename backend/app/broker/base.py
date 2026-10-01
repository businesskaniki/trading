from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
)


class BrokerAdapter(ABC):
    """
    Abstract interface for all AQE broker implementations.

    AQE communicates with this interface rather than directly
    communicating with MT5, paper trading, Binance, or another
    broker.

    Concrete broker adapters are responsible for translating AQE's
    broker-agnostic contracts into broker-specific requests and
    normalizing broker responses back into AQE contracts.

    The adapter layer must not:
        - generate trading signals;
        - run strategies;
        - evaluate risk;
        - create AQE Order database records;
        - manage execution persistence;
        - decide whether a strategy is allowed to trade.
    """

    # ==================================================================
    # CONNECTION
    # ==================================================================

    @abstractmethod
    async def connect(
        self,
        credentials: dict[str, Any] | None = None,
    ) -> Any:
        """
        Connect the broker adapter to a broker account.

        Credentials are supplied at runtime where required.

        For MT5, for example, account credentials are supplied by AQE
        to the MT5 Bridge and are not expected to come from the
        bridge's environment configuration.
        """

        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> Any:
        """
        Disconnect from the current broker account/session.
        """

        raise NotImplementedError

    @abstractmethod
    async def connection_status(self) -> Any:
        """
        Return the current broker connection status.
        """

        raise NotImplementedError

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    @abstractmethod
    async def get_account(self) -> Any:
        """
        Retrieve the current broker account state.
        """

        raise NotImplementedError

    # ==================================================================
    # SYMBOLS / MARKET DATA
    # ==================================================================

    @abstractmethod
    async def get_symbols(self) -> Any:
        """
        Retrieve broker-supported symbols.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_symbol(
        self,
        symbol: str,
    ) -> Any:
        """
        Retrieve metadata for a single broker symbol.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_tick(
        self,
        symbol: str,
    ) -> Any:
        """
        Retrieve the latest broker tick for a symbol.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M15",
        count: int = 200,
    ) -> Any:
        """
        Retrieve recent broker OHLC candles.
        """

        raise NotImplementedError

    # ==================================================================
    # ORDERS
    # ==================================================================

    @abstractmethod
    async def get_orders(self) -> Any:
        """
        Retrieve currently active/pending broker orders.
        """

        raise NotImplementedError

    @abstractmethod
    async def place_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Submit a normalized AQE execution order to the broker.

        The order is broker-agnostic.

        The concrete adapter is responsible for:

            ExecutionOrder
                ↓
            broker-specific request
                ↓
            broker response
                ↓
            ExecutionResult

        The adapter must not perform AQE risk evaluation or strategy
        logic.

        The returned ExecutionResult represents the broker-confirmed
        result of the submission/execution attempt.
        """

        raise NotImplementedError

    @abstractmethod
    async def create_pending_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Submit a LIMIT or STOP order directly to the broker.

        This exists as an explicit broker operation for callers that
        need to create pending orders directly.

        The normal ExecutionEngine path should generally call
        place_order(), allowing the concrete adapter to dispatch
        according to ExecutionOrder.order_type.
        """

        raise NotImplementedError

    # ==================================================================
    # POSITIONS
    # ==================================================================

    @abstractmethod
    async def get_positions(self) -> Any:
        """
        Retrieve all open broker positions.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Retrieve a single broker position.
        """

        raise NotImplementedError

    @abstractmethod
    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Any:
        """
        Modify broker-side position protection.

        At least one of stop-loss or take-profit may be supplied by
        concrete implementations.
        """

        raise NotImplementedError

    @abstractmethod
    async def close_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Close an existing broker position.
        """

        raise NotImplementedError

    # ==================================================================
    # HISTORY
    # ==================================================================

    @abstractmethod
    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ) -> Any:
        """
        Retrieve historical broker orders within a time range.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ) -> Any:
        """
        Retrieve historical broker deals within a time range.
        """

        raise NotImplementedError

    @abstractmethod
    async def get_deals_by_position(
        self,
        position_id: int,
    ) -> Any:
        """
        Retrieve broker deals associated with a position.
        """

        raise NotImplementedError
