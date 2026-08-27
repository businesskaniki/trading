"""Broker exceptions for the Athena Quant Engine.

This module defines the normalized exception hierarchy used by the AQE
broker layer.

Broker adapters should translate broker-specific exceptions into these
AQE exceptions before they reach the rest of the engine.

The hierarchy allows callers to handle errors at different levels.

Example:

    try:
        await broker.submit_order(request)
    except OrderRejectedError:
        ...
    except BrokerConnectionError:
        ...
    except BrokerError:
        ...
"""

from __future__ import annotations

from typing import Any


class BrokerError(Exception):
    """Base exception for all broker-layer failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"

        return self.message


# ============================================================================
# CONNECTION
# ============================================================================


class BrokerConnectionError(BrokerError):
    """Raised when a broker connection cannot be established."""

    def __init__(
        self,
        message: str = "Unable to connect to broker.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="BROKER_CONNECTION_ERROR",
            **kwargs,
        )


class BrokerDisconnectedError(BrokerConnectionError):
    """Raised when an operation requires an active broker connection."""

    def __init__(
        self,
        message: str = "Broker is disconnected.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            **kwargs,
        )


class BrokerAuthenticationError(BrokerConnectionError):
    """Raised when broker authentication fails."""

    def __init__(
        self,
        message: str = "Broker authentication failed.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            **kwargs,
        )


class BrokerTimeoutError(BrokerError):
    """Raised when a broker operation times out."""

    def __init__(
        self,
        message: str = "Broker operation timed out.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="BROKER_TIMEOUT",
            **kwargs,
        )


# ============================================================================
# ACCOUNT
# ============================================================================


class AccountError(BrokerError):
    """Base exception for account-related broker errors."""


class AccountNotFoundError(AccountError):
    """Raised when the requested broker account cannot be found."""

    def __init__(
        self,
        message: str = "Broker account not found.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="ACCOUNT_NOT_FOUND",
            **kwargs,
        )


class AccountAccessError(AccountError):
    """Raised when account information cannot be accessed."""

    def __init__(
        self,
        message: str = "Unable to access broker account.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="ACCOUNT_ACCESS_ERROR",
            **kwargs,
        )


# ============================================================================
# SYMBOL / MARKET DATA
# ============================================================================


class MarketDataError(BrokerError):
    """Base exception for market-data failures."""


class SymbolError(MarketDataError):
    """Base exception for symbol-related failures."""


class SymbolNotFoundError(SymbolError):
    """Raised when a trading symbol does not exist."""

    def __init__(
        self,
        symbol: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            f"Trading symbol '{symbol}' was not found.",
            code="SYMBOL_NOT_FOUND",
            details={
                "symbol": symbol,
                **kwargs.pop("details", {}),
            },
            **kwargs,
        )


class SymbolNotTradeableError(SymbolError):
    """Raised when a symbol exists but cannot currently be traded."""

    def __init__(
        self,
        symbol: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            f"Trading symbol '{symbol}' is not currently tradeable.",
            code="SYMBOL_NOT_TRADEABLE",
            details={
                "symbol": symbol,
                **kwargs.pop("details", {}),
            },
            **kwargs,
        )


class MarketDataUnavailableError(MarketDataError):
    """Raised when required market data is unavailable."""

    def __init__(
        self,
        message: str = "Market data is unavailable.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="MARKET_DATA_UNAVAILABLE",
            **kwargs,
        )


# ============================================================================
# ORDERS
# ============================================================================


class OrderError(BrokerError):
    """Base exception for order-related failures."""


class OrderRejectedError(OrderError):
    """Raised when the broker rejects an order."""

    def __init__(
        self,
        message: str = "Order was rejected by the broker.",
        *,
        order_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})

        if order_id is not None:
            details["order_id"] = order_id

        super().__init__(
            message,
            code="ORDER_REJECTED",
            details=details,
            **kwargs,
        )


class OrderNotFoundError(OrderError):
    """Raised when an order cannot be found."""

    def __init__(
        self,
        order_id: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            f"Order '{order_id}' was not found.",
            code="ORDER_NOT_FOUND",
            details={
                "order_id": order_id,
                **kwargs.pop("details", {}),
            },
            **kwargs,
        )


class OrderSubmissionError(OrderError):
    """Raised when an order cannot be submitted."""

    def __init__(
        self,
        message: str = "Order submission failed.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="ORDER_SUBMISSION_ERROR",
            **kwargs,
        )


class OrderCancellationError(OrderError):
    """Raised when an order cannot be cancelled."""

    def __init__(
        self,
        message: str = "Order cancellation failed.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="ORDER_CANCELLATION_ERROR",
            **kwargs,
        )


class OrderModificationError(OrderError):
    """Raised when an order cannot be modified."""

    def __init__(
        self,
        message: str = "Order modification failed.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="ORDER_MODIFICATION_ERROR",
            **kwargs,
        )


class InvalidOrderError(OrderError):
    """Raised when an order request is invalid."""

    def __init__(
        self,
        message: str = "Invalid order request.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="INVALID_ORDER",
            **kwargs,
        )


# ============================================================================
# POSITIONS
# ============================================================================


class PositionError(BrokerError):
    """Base exception for position-related failures."""


class PositionNotFoundError(PositionError):
    """Raised when a position cannot be found."""

    def __init__(
        self,
        position_id: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            f"Position '{position_id}' was not found.",
            code="POSITION_NOT_FOUND",
            details={
                "position_id": position_id,
                **kwargs.pop("details", {}),
            },
            **kwargs,
        )


class PositionCloseError(PositionError):
    """Raised when a position cannot be closed."""

    def __init__(
        self,
        message: str = "Position could not be closed.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="POSITION_CLOSE_ERROR",
            **kwargs,
        )


# ============================================================================
# EXECUTION
# ============================================================================


class ExecutionError(BrokerError):
    """Base exception for execution failures."""


class ExecutionRejectedError(ExecutionError):
    """Raised when execution is rejected by the broker."""

    def __init__(
        self,
        message: str = "Trade execution was rejected.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="EXECUTION_REJECTED",
            **kwargs,
        )


class ExecutionUnavailableError(ExecutionError):
    """Raised when broker execution is temporarily unavailable."""

    def __init__(
        self,
        message: str = "Broker execution is currently unavailable.",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="EXECUTION_UNAVAILABLE",
            **kwargs,
        )


# ============================================================================
# EXPORTS
# ============================================================================


__all__ = [
    "AccountAccessError",
    "AccountError",
    "AccountNotFoundError",
    "BrokerAuthenticationError",
    "BrokerConnectionError",
    "BrokerDisconnectedError",
    "BrokerError",
    "BrokerTimeoutError",
    "ExecutionError",
    "ExecutionRejectedError",
    "ExecutionUnavailableError",
    "InvalidOrderError",
    "MarketDataError",
    "MarketDataUnavailableError",
    "OrderCancellationError",
    "OrderError",
    "OrderModificationError",
    "OrderNotFoundError",
    "OrderRejectedError",
    "OrderSubmissionError",
    "PositionCloseError",
    "PositionError",
    "PositionNotFoundError",
    "SymbolError",
    "SymbolNotFoundError",
    "SymbolNotTradeableError",
]
