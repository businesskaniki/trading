"""Event subscription utilities for the Athena Quant Engine.

The subscriber provides a high-level interface for AQE components to
listen for events without directly managing the internal subscription
mechanics of the EventBus.
"""

from __future__ import annotations

from typing import Any

from engine.events.bus import EventBus, EventHandler
from engine.events.event_types import EventType


class EventSubscriber:
    """High-level subscription interface for AQE components."""

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
        """Return the subscriber source."""

        return self._source

    # ------------------------------------------------------------------
    # Generic subscription
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> None:
        """Subscribe a handler to an event type."""

        await self._event_bus.subscribe(
            event_type,
            handler,
        )

    async def unsubscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> bool:
        """Remove a handler from an event type."""

        return await self._event_bus.unsubscribe(
            event_type,
            handler,
        )

    async def unsubscribe_all(
        self,
        event_type: EventType | str | None = None,
    ) -> None:
        """Remove subscriptions.

        If no event type is supplied, all subscriptions are removed.
        """

        await self._event_bus.unsubscribe_all(
            event_type,
        )

    # ------------------------------------------------------------------
    # Wildcard
    # ------------------------------------------------------------------

    async def subscribe_all(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to every event published through the bus."""

        await self._event_bus.subscribe(
            EventBus.WILDCARD,
            handler,
        )

    async def unsubscribe_all_events(
        self,
        handler: EventHandler,
    ) -> bool:
        """Remove a wildcard subscription."""

        return await self._event_bus.unsubscribe(
            EventBus.WILDCARD,
            handler,
        )

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    async def on_engine_started(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to engine-started events."""

        await self.subscribe(
            EventType.ENGINE_STARTED,
            handler,
        )

    async def on_engine_stopped(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to engine-stopped events."""

        await self.subscribe(
            EventType.ENGINE_STOPPED,
            handler,
        )

    async def on_engine_paused(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to engine-paused events."""

        await self.subscribe(
            EventType.ENGINE_PAUSED,
            handler,
        )

    async def on_engine_resumed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to engine-resumed events."""

        await self.subscribe(
            EventType.ENGINE_RESUMED,
            handler,
        )

    async def on_engine_failed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to engine-failure events."""

        await self.subscribe(
            EventType.ENGINE_FAILED,
            handler,
        )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def on_market_data_received(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to generic market-data events."""

        await self.subscribe(
            EventType.MARKET_DATA_RECEIVED,
            handler,
        )

    async def on_tick_received(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to tick events."""

        await self.subscribe(
            EventType.TICK_RECEIVED,
            handler,
        )

    async def on_candle_received(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to candle events."""

        await self.subscribe(
            EventType.CANDLE_RECEIVED,
            handler,
        )

    async def on_market_session_opened(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to market-session-open events."""

        await self.subscribe(
            EventType.MARKET_SESSION_OPENED,
            handler,
        )

    async def on_market_session_closed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to market-session-close events."""

        await self.subscribe(
            EventType.MARKET_SESSION_CLOSED,
            handler,
        )

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    async def on_strategy_started(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to strategy-started events."""

        await self.subscribe(
            EventType.STRATEGY_STARTED,
            handler,
        )

    async def on_strategy_stopped(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to strategy-stopped events."""

        await self.subscribe(
            EventType.STRATEGY_STOPPED,
            handler,
        )

    async def on_signal_generated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to generated trading signals."""

        await self.subscribe(
            EventType.SIGNAL_GENERATED,
            handler,
        )

    async def on_signal_rejected(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to rejected trading signals."""

        await self.subscribe(
            EventType.SIGNAL_REJECTED,
            handler,
        )

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------

    async def on_risk_check_started(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to risk-check-started events."""

        await self.subscribe(
            EventType.RISK_CHECK_STARTED,
            handler,
        )

    async def on_risk_check_passed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to successful risk checks."""

        await self.subscribe(
            EventType.RISK_CHECK_PASSED,
            handler,
        )

    async def on_risk_check_failed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to failed risk checks."""

        await self.subscribe(
            EventType.RISK_CHECK_FAILED,
            handler,
        )

    async def on_risk_limit_breached(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to risk-limit breaches."""

        await self.subscribe(
            EventType.RISK_LIMIT_BREACHED,
            handler,
        )

    async def on_drawdown_limit_breached(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to drawdown-limit breaches."""

        await self.subscribe(
            EventType.DRAWDOWN_LIMIT_BREACHED,
            handler,
        )

    async def on_exposure_limit_breached(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to exposure-limit breaches."""

        await self.subscribe(
            EventType.EXPOSURE_LIMIT_BREACHED,
            handler,
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def on_order_created(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-created events."""

        await self.subscribe(
            EventType.ORDER_CREATED,
            handler,
        )

    async def on_order_submitted(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-submitted events."""

        await self.subscribe(
            EventType.ORDER_SUBMITTED,
            handler,
        )

    async def on_order_accepted(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-accepted events."""

        await self.subscribe(
            EventType.ORDER_ACCEPTED,
            handler,
        )

    async def on_order_rejected(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-rejected events."""

        await self.subscribe(
            EventType.ORDER_REJECTED,
            handler,
        )

    async def on_order_cancel_requested(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-cancel-requested events."""

        await self.subscribe(
            EventType.ORDER_CANCEL_REQUESTED,
            handler,
        )

    async def on_order_cancelled(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-cancelled events."""

        await self.subscribe(
            EventType.ORDER_CANCELLED,
            handler,
        )

    async def on_order_modified(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to order-modified events."""

        await self.subscribe(
            EventType.ORDER_MODIFIED,
            handler,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def on_execution_started(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to execution-started events."""

        await self.subscribe(
            EventType.EXECUTION_STARTED,
            handler,
        )

    async def on_execution_completed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to execution-completed events."""

        await self.subscribe(
            EventType.EXECUTION_COMPLETED,
            handler,
        )

    async def on_execution_failed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to execution-failed events."""

        await self.subscribe(
            EventType.EXECUTION_FAILED,
            handler,
        )

    async def on_order_filled(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to fully-filled orders."""

        await self.subscribe(
            EventType.ORDER_FILLED,
            handler,
        )

    async def on_partial_fill(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to partial fills."""

        await self.subscribe(
            EventType.PARTIAL_FILL,
            handler,
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def on_position_opened(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to position-opened events."""

        await self.subscribe(
            EventType.POSITION_OPENED,
            handler,
        )

    async def on_position_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to position-updated events."""

        await self.subscribe(
            EventType.POSITION_UPDATED,
            handler,
        )

    async def on_position_closed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to position-closed events."""

        await self.subscribe(
            EventType.POSITION_CLOSED,
            handler,
        )

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def on_portfolio_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to portfolio updates."""

        await self.subscribe(
            EventType.PORTFOLIO_UPDATED,
            handler,
        )

    async def on_equity_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to equity updates."""

        await self.subscribe(
            EventType.EQUITY_UPDATED,
            handler,
        )

    async def on_balance_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to balance updates."""

        await self.subscribe(
            EventType.BALANCE_UPDATED,
            handler,
        )

    async def on_pnl_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to P&L updates."""

        await self.subscribe(
            EventType.PNL_UPDATED,
            handler,
        )

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def on_metrics_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to analytics-metrics updates."""

        await self.subscribe(
            EventType.METRICS_UPDATED,
            handler,
        )

    async def on_performance_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to performance updates."""

        await self.subscribe(
            EventType.PERFORMANCE_UPDATED,
            handler,
        )

    async def on_equity_curve_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to equity-curve updates."""

        await self.subscribe(
            EventType.EQUITY_CURVE_UPDATED,
            handler,
        )

    # ------------------------------------------------------------------
    # Backtesting
    # ------------------------------------------------------------------

    async def on_backtest_started(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to backtest-started events."""

        await self.subscribe(
            EventType.BACKTEST_STARTED,
            handler,
        )

    async def on_backtest_completed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to backtest-completed events."""

        await self.subscribe(
            EventType.BACKTEST_COMPLETED,
            handler,
        )

    async def on_backtest_failed(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to backtest-failed events."""

        await self.subscribe(
            EventType.BACKTEST_FAILED,
            handler,
        )

    # ------------------------------------------------------------------
    # ML
    # ------------------------------------------------------------------

    async def on_ml_prediction_generated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to ML predictions."""

        await self.subscribe(
            EventType.ML_PREDICTION_GENERATED,
            handler,
        )

    async def on_ml_model_updated(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to ML model updates."""

        await self.subscribe(
            EventType.ML_MODEL_UPDATED,
            handler,
        )

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    async def on_health_check(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to health-check events."""

        await self.subscribe(
            EventType.HEALTH_CHECK,
            handler,
        )

    async def on_error(
        self,
        handler: EventHandler,
    ) -> None:
        """Subscribe to system error events."""

        await self.subscribe(
            EventType.ERROR,
            handler,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    async def subscriptions(self) -> dict[str, int]:
        """Return the current subscription counts."""

        return await self._event_bus.subscriptions()


__all__ = [
    "EventSubscriber",
]
