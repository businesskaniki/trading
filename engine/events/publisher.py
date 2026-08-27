"""Event publishing utilities for the Athena Quant Engine.

The publisher provides a higher-level interface over the EventBus.

Subsystems such as strategy, risk, execution, portfolio, and market data
can use this class without needing to know the internal implementation of
the event bus.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from engine.events.bus import EventBus, EventPublishResult
from engine.events.event_types import (
    Event,
    EventType,
    ExecutionEvent,
    MarketEvent,
    OrderEvent,
    PortfolioEvent,
    PositionEvent,
    RiskEvent,
    SignalEvent,
)

logger = logging.getLogger(__name__)


class EventPublisher:
    """High-level event publisher for AQE subsystems."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        source: str | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._source = source

    @property
    def event_bus(self) -> EventBus:
        """Return the underlying event bus."""

        return self._event_bus

    @property
    def source(self) -> str | None:
        """Return the default event source."""

        return self._source

    # ------------------------------------------------------------------
    # Generic publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        event: Event,
    ) -> EventPublishResult:
        """Publish an already-created event."""

        if event.source is None and self._source is not None:
            event.source = self._source

        return await self._event_bus.publish(event)

    async def emit(
        self,
        event_type: EventType,
        *,
        data: dict[str, Any] | None = None,
        source: str | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Create and publish a generic event."""

        event = Event(
            event_type=event_type,
            data=data or {},
            source=source or self._source,
            correlation_id=correlation_id,
            causation_id=causation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    async def engine_started(
        self,
        *,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an engine-started event."""

        return await self.emit(
            EventType.ENGINE_STARTED,
            data=data,
            metadata=metadata,
        )

    async def engine_stopped(
        self,
        *,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an engine-stopped event."""

        return await self.emit(
            EventType.ENGINE_STOPPED,
            data=data,
            metadata=metadata,
        )

    async def engine_paused(
        self,
        *,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an engine-paused event."""

        return await self.emit(
            EventType.ENGINE_PAUSED,
            data=data,
            metadata=metadata,
        )

    async def engine_resumed(
        self,
        *,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an engine-resumed event."""

        return await self.emit(
            EventType.ENGINE_RESUMED,
            data=data,
            metadata=metadata,
        )

    async def engine_failed(
        self,
        *,
        error: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an engine-failure event."""

        payload = {
            "error": error,
            **(data or {}),
        }

        return await self.emit(
            EventType.ENGINE_FAILED,
            data=payload,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def market_data_received(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a market-data event."""

        event = MarketEvent(
            event_type=EventType.MARKET_DATA_RECEIVED,
            symbol=symbol,
            timeframe=timeframe,
            data=data or {},
            source=self._source,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def tick_received(
        self,
        *,
        symbol: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a tick event."""

        event = MarketEvent(
            event_type=EventType.TICK_RECEIVED,
            symbol=symbol,
            data=data,
            source=self._source,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def candle_received(
        self,
        *,
        symbol: str,
        timeframe: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a candle event."""

        event = MarketEvent(
            event_type=EventType.CANDLE_RECEIVED,
            symbol=symbol,
            timeframe=timeframe,
            data=data,
            source=self._source,
            metadata=metadata or {},
        )

        return await self.publish(event)

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    async def signal_generated(
        self,
        *,
        strategy: str,
        symbol: str,
        signal: str,
        confidence: float | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a strategy signal."""

        event = SignalEvent(
            event_type=EventType.SIGNAL_GENERATED,
            strategy=strategy,
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def signal_rejected(
        self,
        *,
        strategy: str,
        symbol: str,
        reason: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a rejected strategy signal."""

        payload = {
            "reason": reason,
            **(data or {}),
        }

        event = SignalEvent(
            event_type=EventType.SIGNAL_REJECTED,
            strategy=strategy,
            symbol=symbol,
            data=payload,
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------

    async def risk_check_passed(
        self,
        *,
        symbol: str | None = None,
        rule: str | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a successful risk-check event."""

        event = RiskEvent(
            event_type=EventType.RISK_CHECK_PASSED,
            symbol=symbol,
            rule=rule,
            approved=True,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def risk_check_failed(
        self,
        *,
        symbol: str | None = None,
        rule: str | None = None,
        reason: str | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a failed risk-check event."""

        event = RiskEvent(
            event_type=EventType.RISK_CHECK_FAILED,
            symbol=symbol,
            rule=rule,
            approved=False,
            reason=reason,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def risk_limit_breached(
        self,
        *,
        rule: str,
        reason: str,
        symbol: str | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a risk-limit breach."""

        payload = {
            "reason": reason,
            **(data or {}),
        }

        event = RiskEvent(
            event_type=EventType.RISK_LIMIT_BREACHED,
            rule=rule,
            symbol=symbol,
            approved=False,
            reason=reason,
            data=payload,
            source=self._source,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def drawdown_limit_breached(
        self,
        *,
        drawdown: float,
        limit: float,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a drawdown-limit breach."""

        payload = {
            "drawdown": drawdown,
            "limit": limit,
            **(data or {}),
        }

        return await self.emit(
            EventType.DRAWDOWN_LIMIT_BREACHED,
            data=payload,
            metadata=metadata,
        )

    async def exposure_limit_breached(
        self,
        *,
        exposure: float,
        limit: float,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an exposure-limit breach."""

        payload = {
            "exposure": exposure,
            "limit": limit,
            **(data or {}),
        }

        return await self.emit(
            EventType.EXPOSURE_LIMIT_BREACHED,
            data=payload,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def order_created(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an order-created event."""

        event = OrderEvent(
            event_type=EventType.ORDER_CREATED,
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def order_submitted(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an order-submitted event."""

        event = OrderEvent(
            event_type=EventType.ORDER_SUBMITTED,
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def order_accepted(
        self,
        *,
        order_id: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an order-accepted event."""

        return await self.emit(
            EventType.ORDER_ACCEPTED,
            data={
                "order_id": order_id,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def order_rejected(
        self,
        *,
        order_id: str,
        reason: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an order-rejected event."""

        return await self.emit(
            EventType.ORDER_REJECTED,
            data={
                "order_id": order_id,
                "reason": reason,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def order_cancelled(
        self,
        *,
        order_id: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an order-cancelled event."""

        return await self.emit(
            EventType.ORDER_CANCELLED,
            data={
                "order_id": order_id,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execution_started(
        self,
        *,
        order_id: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an execution-started event."""

        return await self.emit(
            EventType.EXECUTION_STARTED,
            data={
                "order_id": order_id,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def order_filled(
        self,
        *,
        order_id: str,
        execution_id: str | None,
        symbol: str,
        quantity: float,
        price: float,
        slippage: float | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a fully-filled order event."""

        event = ExecutionEvent(
            event_type=EventType.ORDER_FILLED,
            order_id=order_id,
            execution_id=execution_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            slippage=slippage,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def partial_fill(
        self,
        *,
        order_id: str,
        execution_id: str | None,
        symbol: str,
        quantity: float,
        price: float,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a partial-fill event."""

        event = ExecutionEvent(
            event_type=EventType.PARTIAL_FILL,
            order_id=order_id,
            execution_id=execution_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def execution_completed(
        self,
        *,
        order_id: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an execution-completed event."""

        return await self.emit(
            EventType.EXECUTION_COMPLETED,
            data={
                "order_id": order_id,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def execution_failed(
        self,
        *,
        order_id: str,
        reason: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an execution-failed event."""

        return await self.emit(
            EventType.EXECUTION_FAILED,
            data={
                "order_id": order_id,
                "reason": reason,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def position_opened(
        self,
        *,
        position_id: str,
        symbol: str,
        quantity: float,
        average_price: float,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a position-opened event."""

        event = PositionEvent(
            event_type=EventType.POSITION_OPENED,
            position_id=position_id,
            symbol=symbol,
            quantity=quantity,
            average_price=average_price,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def position_updated(
        self,
        *,
        position_id: str,
        symbol: str,
        quantity: float,
        average_price: float,
        unrealized_pnl: float | None = None,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a position-updated event."""

        event = PositionEvent(
            event_type=EventType.POSITION_UPDATED,
            position_id=position_id,
            symbol=symbol,
            quantity=quantity,
            average_price=average_price,
            unrealized_pnl=unrealized_pnl,
            data=data or {},
            source=self._source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def position_closed(
        self,
        *,
        position_id: str,
        symbol: str,
        data: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a position-closed event."""

        return await self.emit(
            EventType.POSITION_CLOSED,
            data={
                "position_id": position_id,
                "symbol": symbol,
                **(data or {}),
            },
            correlation_id=correlation_id,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def portfolio_updated(
        self,
        *,
        account_id: str | None = None,
        equity: float | None = None,
        balance: float | None = None,
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a portfolio update."""

        event = PortfolioEvent(
            event_type=EventType.PORTFOLIO_UPDATED,
            account_id=account_id,
            equity=equity,
            balance=balance,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            data=data or {},
            source=self._source,
            metadata=metadata or {},
        )

        return await self.publish(event)

    async def equity_updated(
        self,
        *,
        equity: float,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish an equity update."""

        return await self.emit(
            EventType.EQUITY_UPDATED,
            data={
                "equity": equity,
                **(data or {}),
            },
            metadata=metadata,
        )

    async def balance_updated(
        self,
        *,
        balance: float,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a balance update."""

        return await self.emit(
            EventType.BALANCE_UPDATED,
            data={
                "balance": balance,
                **(data or {}),
            },
            metadata=metadata,
        )

    async def pnl_updated(
        self,
        *,
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventPublishResult:
        """Publish a P&L update."""

        return await self.emit(
            EventType.PNL_UPDATED,
            data={
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                **(data or {}),
            },
            metadata=metadata,
        )


__all__ = [
    "EventPublisher",
]
