"""Event handlers for the Athena Quant Engine.

Handlers contain reactions to AQE events.

They are intentionally lightweight orchestration components. Core trading
logic remains inside the strategy, risk, execution, portfolio, analytics,
and monitoring subsystems.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable

from engine.events.event_types import (
    Event,
    EventType,
    ExecutionEvent,
    OrderEvent,
    PortfolioEvent,
    PositionEvent,
    RiskEvent,
    SignalEvent,
)

logger = logging.getLogger(__name__)


AsyncOrSyncCallable = Callable[..., Any | Awaitable[Any]]


class EventHandler:
    """Base class for AQE event handlers.

    Handler instances are callable so they can be registered directly
    with the EventBus.
    """

    name = "event_handler"

    async def handle(self, event: Event) -> None:
        """Handle an event.

        Subclasses should override this method.
        """

        raise NotImplementedError

    async def __call__(self, event: Event) -> None:
        """Allow the handler instance to be used as a callable."""

        await self.handle(event)


class LoggingEventHandler(EventHandler):
    """Logs incoming AQE events."""

    name = "logging_handler"

    def __init__(
        self,
        *,
        logger_instance: logging.Logger | None = None,
        level: int = logging.INFO,
    ) -> None:
        self._logger = logger_instance or logger
        self._level = level

    async def handle(self, event: Event) -> None:
        """Log an incoming event."""

        self._logger.log(
            self._level,
            "AQE event: type=%s id=%s source=%s data=%s",
            event.event_type.value,
            event.event_id,
            event.source,
            event.data,
        )


class EngineLifecycleHandler(EventHandler):
    """Handles engine lifecycle events."""

    name = "engine_lifecycle_handler"

    async def handle(self, event: Event) -> None:
        """Handle engine lifecycle events."""

        if event.event_type == EventType.ENGINE_STARTED:
            logger.info("AQE engine started.")

        elif event.event_type == EventType.ENGINE_STOPPED:
            logger.info("AQE engine stopped.")

        elif event.event_type == EventType.ENGINE_PAUSED:
            logger.warning("AQE engine paused.")

        elif event.event_type == EventType.ENGINE_RESUMED:
            logger.info("AQE engine resumed.")

        elif event.event_type == EventType.ENGINE_FAILED:
            logger.critical(
                "AQE engine failure: %s",
                event.data,
            )


class SignalEventHandler(EventHandler):
    """Handles strategy signal events.

    This handler does not execute trades. It delegates the signal to
    the configured callback, normally the risk subsystem.
    """

    name = "signal_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: SignalEvent | Event,
    ) -> None:
        """Process a strategy signal."""

        if event.event_type not in {
            EventType.SIGNAL_GENERATED,
            EventType.SIGNAL_REJECTED,
        }:
            return

        await _execute_callback(
            self._callback,
            event,
        )


class RiskEventHandler(EventHandler):
    """Handles risk subsystem events."""

    name = "risk_event_handler"

    def __init__(
        self,
        on_passed: AsyncOrSyncCallable | None = None,
        on_failed: AsyncOrSyncCallable | None = None,
        on_breach: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._on_passed = on_passed
        self._on_failed = on_failed
        self._on_breach = on_breach

    async def handle(
        self,
        event: RiskEvent | Event,
    ) -> None:
        """React to risk events."""

        if event.event_type == EventType.RISK_CHECK_PASSED:
            callback = self._on_passed

        elif event.event_type == EventType.RISK_CHECK_FAILED:
            callback = self._on_failed

        elif event.event_type in {
            EventType.RISK_LIMIT_BREACHED,
            EventType.DRAWDOWN_LIMIT_BREACHED,
            EventType.EXPOSURE_LIMIT_BREACHED,
        }:
            callback = self._on_breach

        else:
            return

        if callback is None:
            logger.warning(
                "Risk event received: type=%s data=%s",
                event.event_type.value,
                event.data,
            )
            return

        await _execute_callback(
            callback,
            event,
        )


class OrderEventHandler(EventHandler):
    """Handles order lifecycle events."""

    name = "order_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: OrderEvent | Event,
    ) -> None:
        """React to order lifecycle events."""

        order_events = {
            EventType.ORDER_CREATED,
            EventType.ORDER_SUBMITTED,
            EventType.ORDER_ACCEPTED,
            EventType.ORDER_REJECTED,
            EventType.ORDER_CANCEL_REQUESTED,
            EventType.ORDER_CANCELLED,
            EventType.ORDER_MODIFIED,
        }

        if event.event_type not in order_events:
            return

        if self._callback is None:
            logger.info(
                "Order event: type=%s order_id=%s",
                event.event_type.value,
                getattr(event, "order_id", None),
            )
            return

        await _execute_callback(
            self._callback,
            event,
        )


class ExecutionEventHandler(EventHandler):
    """Handles execution events."""

    name = "execution_event_handler"

    def __init__(
        self,
        on_fill: AsyncOrSyncCallable | None = None,
        on_partial_fill: AsyncOrSyncCallable | None = None,
        on_failure: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._on_fill = on_fill
        self._on_partial_fill = on_partial_fill
        self._on_failure = on_failure

    async def handle(
        self,
        event: ExecutionEvent | Event,
    ) -> None:
        """React to execution events."""

        if event.event_type == EventType.ORDER_FILLED:
            callback = self._on_fill

        elif event.event_type == EventType.PARTIAL_FILL:
            callback = self._on_partial_fill

        elif event.event_type == EventType.EXECUTION_FAILED:
            callback = self._on_failure

        else:
            return

        if callback is None:
            logger.info(
                "Execution event: type=%s order_id=%s",
                event.event_type.value,
                getattr(event, "order_id", None),
            )
            return

        await _execute_callback(
            callback,
            event,
        )


class PositionEventHandler(EventHandler):
    """Handles position lifecycle events."""

    name = "position_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: PositionEvent | Event,
    ) -> None:
        """React to position events."""

        position_events = {
            EventType.POSITION_OPENED,
            EventType.POSITION_UPDATED,
            EventType.POSITION_CLOSED,
        }

        if event.event_type not in position_events:
            return

        if self._callback is None:
            logger.info(
                "Position event: type=%s position_id=%s symbol=%s",
                event.event_type.value,
                getattr(event, "position_id", None),
                getattr(event, "symbol", None),
            )
            return

        await _execute_callback(
            self._callback,
            event,
        )


class PortfolioEventHandler(EventHandler):
    """Handles portfolio state updates."""

    name = "portfolio_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: PortfolioEvent | Event,
    ) -> None:
        """React to portfolio events."""

        portfolio_events = {
            EventType.PORTFOLIO_UPDATED,
            EventType.EQUITY_UPDATED,
            EventType.BALANCE_UPDATED,
            EventType.PNL_UPDATED,
        }

        if event.event_type not in portfolio_events:
            return

        if self._callback is None:
            logger.debug(
                "Portfolio event: type=%s data=%s",
                event.event_type.value,
                event.data,
            )
            return

        await _execute_callback(
            self._callback,
            event,
        )


class AnalyticsEventHandler(EventHandler):
    """Handles events used to update analytics."""

    name = "analytics_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: Event,
    ) -> None:
        """React to analytics-relevant events."""

        analytics_events = {
            EventType.POSITION_OPENED,
            EventType.POSITION_UPDATED,
            EventType.POSITION_CLOSED,
            EventType.ORDER_FILLED,
            EventType.PORTFOLIO_UPDATED,
            EventType.EQUITY_UPDATED,
            EventType.PNL_UPDATED,
        }

        if event.event_type not in analytics_events:
            return

        if self._callback is None:
            logger.debug(
                "Analytics event received: %s",
                event.event_type.value,
            )
            return

        await _execute_callback(
            self._callback,
            event,
        )


class MonitoringEventHandler(EventHandler):
    """Handles system events for monitoring and observability."""

    name = "monitoring_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: Event,
    ) -> None:
        """Process monitoring-relevant events."""

        monitoring_events = {
            EventType.ENGINE_STARTED,
            EventType.ENGINE_STOPPED,
            EventType.ENGINE_FAILED,
            EventType.RISK_LIMIT_BREACHED,
            EventType.DRAWDOWN_LIMIT_BREACHED,
            EventType.EXPOSURE_LIMIT_BREACHED,
            EventType.ORDER_REJECTED,
            EventType.EXECUTION_FAILED,
            EventType.ERROR,
        }

        if event.event_type not in monitoring_events:
            return

        if self._callback is None:
            logger.warning(
                "Monitoring event: type=%s data=%s",
                event.event_type.value,
                event.data,
            )
            return

        await _execute_callback(
            self._callback,
            event,
        )


class ErrorEventHandler(EventHandler):
    """Handles system error events."""

    name = "error_event_handler"

    def __init__(
        self,
        callback: AsyncOrSyncCallable | None = None,
    ) -> None:
        self._callback = callback

    async def handle(
        self,
        event: Event,
    ) -> None:
        """Handle an AQE system error."""

        if event.event_type != EventType.ERROR:
            return

        logger.error(
            "AQE system error: %s",
            event.data,
        )

        await _execute_callback(
            self._callback,
            event,
        )


def create_default_handlers(
    *,
    signal_callback: AsyncOrSyncCallable | None = None,
    risk_passed_callback: AsyncOrSyncCallable | None = None,
    risk_failed_callback: AsyncOrSyncCallable | None = None,
    risk_breach_callback: AsyncOrSyncCallable | None = None,
    order_callback: AsyncOrSyncCallable | None = None,
    fill_callback: AsyncOrSyncCallable | None = None,
    partial_fill_callback: AsyncOrSyncCallable | None = None,
    execution_failure_callback: AsyncOrSyncCallable | None = None,
    position_callback: AsyncOrSyncCallable | None = None,
    portfolio_callback: AsyncOrSyncCallable | None = None,
    analytics_callback: AsyncOrSyncCallable | None = None,
    monitoring_callback: AsyncOrSyncCallable | None = None,
    error_callback: AsyncOrSyncCallable | None = None,
) -> list[EventHandler]:
    """Create the standard AQE event-handler set."""

    return [
        LoggingEventHandler(),
        EngineLifecycleHandler(),
        SignalEventHandler(
            callback=signal_callback,
        ),
        RiskEventHandler(
            on_passed=risk_passed_callback,
            on_failed=risk_failed_callback,
            on_breach=risk_breach_callback,
        ),
        OrderEventHandler(
            callback=order_callback,
        ),
        ExecutionEventHandler(
            on_fill=fill_callback,
            on_partial_fill=partial_fill_callback,
            on_failure=execution_failure_callback,
        ),
        PositionEventHandler(
            callback=position_callback,
        ),
        PortfolioEventHandler(
            callback=portfolio_callback,
        ),
        AnalyticsEventHandler(
            callback=analytics_callback,
        ),
        MonitoringEventHandler(
            callback=monitoring_callback,
        ),
        ErrorEventHandler(
            callback=error_callback,
        ),
    ]


async def _execute_callback(
    callback: AsyncOrSyncCallable | None,
    event: Event,
) -> None:
    """Execute a synchronous or asynchronous callback safely."""

    if callback is None:
        return

    result = callback(event)

    if inspect.isawaitable(result):
        await result


__all__ = [
    "AnalyticsEventHandler",
    "EngineLifecycleHandler",
    "ErrorEventHandler",
    "EventHandler",
    "ExecutionEventHandler",
    "LoggingEventHandler",
    "MonitoringEventHandler",
    "OrderEventHandler",
    "PortfolioEventHandler",
    "PositionEventHandler",
    "RiskEventHandler",
    "SignalEventHandler",
    "create_default_handlers",
]
