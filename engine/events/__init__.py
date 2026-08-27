"""Event-driven infrastructure for the Athena Quant Engine.

This package provides:

- Event definitions and event types.
- The central event bus.
- Event publishing utilities.
- Event subscription utilities.
- Standard event handlers.
"""

from engine.events.bus import EventBus, EventHandler, EventPublishResult
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
from engine.events.handlers import (
    AnalyticsEventHandler,
    EngineLifecycleHandler,
    ErrorEventHandler,
    ExecutionEventHandler,
    LoggingEventHandler,
    MonitoringEventHandler,
    OrderEventHandler,
    PortfolioEventHandler,
    PositionEventHandler,
    RiskEventHandler,
    SignalEventHandler,
    create_default_handlers,
)
from engine.events.publisher import EventPublisher
from engine.events.subscriber import EventSubscriber

__all__ = [
    # Core event infrastructure
    "Event",
    "EventType",
    "EventBus",
    "EventHandler",
    "EventPublishResult",
    # Specialized events
    "MarketEvent",
    "SignalEvent",
    "RiskEvent",
    "OrderEvent",
    "ExecutionEvent",
    "PositionEvent",
    "PortfolioEvent",
    # Publisher / subscriber
    "EventPublisher",
    "EventSubscriber",
    # Handlers
    "AnalyticsEventHandler",
    "EngineLifecycleHandler",
    "ErrorEventHandler",
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
