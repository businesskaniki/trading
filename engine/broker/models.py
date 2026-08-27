"""Broker data models for the Athena Quant Engine.

These models define the normalized data exchanged between the AQE engine
and broker adapters.

They are intentionally independent of:
    - MetaTrader 5
    - SQLAlchemy
    - FastAPI
    - API request/response schemas

Broker adapters are responsible for converting broker-specific data into
these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

# ============================================================================
# ENUMS
# ============================================================================


class OrderSide(StrEnum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    """Normalized order lifecycle states."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class PositionSide(StrEnum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


# ============================================================================
# ACCOUNT
# ============================================================================


@dataclass(slots=True)
class AccountInfo:
    """Normalized broker account information."""

    account_id: str
    balance: float
    equity: float
    currency: str

    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float | None = None

    leverage: int | None = None

    broker: str | None = None
    server: str | None = None

    is_demo: bool = False

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# SYMBOL
# ============================================================================


@dataclass(slots=True)
class SymbolInfo:
    """Normalized trading-symbol specification."""

    symbol: str

    description: str | None = None
    base_currency: str | None = None
    quote_currency: str | None = None

    digits: int = 5

    tick_size: float = 0.0
    tick_value: float = 0.0

    contract_size: float = 0.0

    min_volume: float = 0.0
    max_volume: float = 0.0
    volume_step: float = 0.0

    min_stop_distance: float | None = None

    tradeable: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )


# ============================================================================
# MARKET DATA
# ============================================================================


@dataclass(slots=True)
class Tick:
    """Normalized real-time bid/ask tick."""

    symbol: str

    bid: float
    ask: float

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    volume: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    @property
    def spread(self) -> float:
        """Return the absolute bid/ask spread."""

        return self.ask - self.bid

    @property
    def mid_price(self) -> float:
        """Return the midpoint between bid and ask."""

        return (self.bid + self.ask) / 2


@dataclass(slots=True)
class Candle:
    """Normalized OHLCV candle."""

    symbol: str
    timeframe: str

    timestamp: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0

    tick_volume: float | None = None
    spread: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )


# ============================================================================
# ORDERS
# ============================================================================


@dataclass(slots=True)
class OrderRequest:
    """Standardized order request sent from AQE to a broker."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float

    price: float | None = None

    stop_loss: float | None = None
    take_profit: float | None = None

    client_order_id: str | None = None

    account_id: str | None = None

    strategy: str | None = None

    correlation_id: UUID | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )


@dataclass(slots=True)
class OrderResult:
    """Normalized result of an order operation."""

    success: bool

    order_id: str | None = None

    status: OrderStatus | None = None

    symbol: str | None = None
    side: OrderSide | None = None

    requested_quantity: float | None = None
    filled_quantity: float = 0.0

    requested_price: float | None = None
    average_fill_price: float | None = None

    message: str | None = None
    error_code: str | None = None

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )


# ============================================================================
# POSITIONS
# ============================================================================


@dataclass(slots=True)
class Position:
    """Normalized open trading position."""

    position_id: str
    symbol: str

    side: PositionSide
    quantity: float

    average_price: float

    current_price: float | None = None

    stop_loss: float | None = None
    take_profit: float | None = None

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    swap: float = 0.0
    commission: float = 0.0

    account_id: str | None = None

    opened_at: datetime | None = None
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )


# ============================================================================
# EXPORTS
# ============================================================================


__all__ = [
    "AccountInfo",
    "Candle",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "SymbolInfo",
    "Tick",
]
