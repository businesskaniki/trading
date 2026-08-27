"""Event definitions for the Athena Quant Engine.

This module contains the standardized event vocabulary used for
communication between AQE subsystems.

Events should describe something that happened or something that has
been requested. They should not contain business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class EventType(StrEnum):
    """Standard AQE event types."""

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"
    ENGINE_PAUSED = "engine.paused"
    ENGINE_RESUMED = "engine.resumed"
    ENGINE_FAILED = "engine.failed"

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    MARKET_DATA_RECEIVED = "market.data.received"
    TICK_RECEIVED = "market.tick.received"
    CANDLE_RECEIVED = "market.candle.received"
    MARKET_SESSION_OPENED = "market.session.opened"
    MARKET_SESSION_CLOSED = "market.session.closed"

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    STRATEGY_STARTED = "strategy.started"
    STRATEGY_STOPPED = "strategy.stopped"
    SIGNAL_GENERATED = "strategy.signal.generated"
    SIGNAL_REJECTED = "strategy.signal.rejected"

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------

    RISK_CHECK_STARTED = "risk.check.started"
    RISK_CHECK_PASSED = "risk.check.passed"
    RISK_CHECK_FAILED = "risk.check.failed"
    RISK_LIMIT_BREACHED = "risk.limit.breached"
    DRAWDOWN_LIMIT_BREACHED = "risk.drawdown_limit.breached"
    EXPOSURE_LIMIT_BREACHED = "risk.exposure_limit.breached"

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    ORDER_CREATED = "order.created"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_REJECTED = "order.rejected"
    ORDER_CANCEL_REQUESTED = "order.cancel_requested"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_MODIFIED = "order.modified"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    ORDER_FILLED = "execution.order_filled"
    PARTIAL_FILL = "execution.partial_fill"

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    POSITION_OPENED = "position.opened"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    PORTFOLIO_UPDATED = "portfolio.updated"
    EQUITY_UPDATED = "portfolio.equity_updated"
    BALANCE_UPDATED = "portfolio.balance_updated"
    PNL_UPDATED = "portfolio.pnl_updated"

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    METRICS_UPDATED = "analytics.metrics_updated"
    PERFORMANCE_UPDATED = "analytics.performance_updated"
    EQUITY_CURVE_UPDATED = "analytics.equity_curve_updated"

    # ------------------------------------------------------------------
    # Backtesting
    # ------------------------------------------------------------------

    BACKTEST_STARTED = "backtest.started"
    BACKTEST_COMPLETED = "backtest.completed"
    BACKTEST_FAILED = "backtest.failed"

    # ------------------------------------------------------------------
    # ML
    # ------------------------------------------------------------------

    ML_PREDICTION_GENERATED = "ml.prediction.generated"
    ML_MODEL_UPDATED = "ml.model.updated"

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    HEALTH_CHECK = "system.health_check"
    ERROR = "system.error"


@dataclass(slots=True)
class Event:
    """Base event exchanged between AQE components."""

    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    event_id: UUID = field(
        default_factory=uuid4,
    )

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    source: str | None = None

    correlation_id: UUID | None = None

    causation_id: UUID | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert the event into a serializable dictionary."""

        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": (
                str(self.correlation_id) if self.correlation_id else None
            ),
            "causation_id": (str(self.causation_id) if self.causation_id else None),
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class MarketEvent(Event):
    """Base event for market-data activity."""

    symbol: str | None = None
    timeframe: str | None = None


@dataclass(slots=True)
class SignalEvent(Event):
    """Event containing a strategy-generated trading signal."""

    strategy: str | None = None
    symbol: str | None = None
    signal: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class RiskEvent(Event):
    """Event generated by the risk subsystem."""

    rule: str | None = None
    symbol: str | None = None
    approved: bool | None = None
    reason: str | None = None


@dataclass(slots=True)
class OrderEvent(Event):
    """Event associated with an order."""

    order_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    quantity: float | None = None
    price: float | None = None


@dataclass(slots=True)
class ExecutionEvent(Event):
    """Event associated with trade execution."""

    order_id: str | None = None
    execution_id: str | None = None
    symbol: str | None = None
    quantity: float | None = None
    price: float | None = None
    slippage: float | None = None


@dataclass(slots=True)
class PositionEvent(Event):
    """Event associated with a position."""

    position_id: str | None = None
    symbol: str | None = None
    quantity: float | None = None
    average_price: float | None = None
    unrealized_pnl: float | None = None


@dataclass(slots=True)
class PortfolioEvent(Event):
    """Event associated with portfolio state."""

    account_id: str | None = None
    equity: float | None = None
    balance: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None


__all__ = [
    "Event",
    "EventType",
    "ExecutionEvent",
    "MarketEvent",
    "OrderEvent",
    "PortfolioEvent",
    "PositionEvent",
    "RiskEvent",
    "SignalEvent",
]
