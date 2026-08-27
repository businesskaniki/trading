"""Asynchronous in-process event bus for the Athena Quant Engine.

The event bus provides decoupled communication between AQE subsystems.

Example:

    event_bus.subscribe(
        EventType.ORDER_FILLED,
        portfolio_handler,
    )

    await event_bus.publish(
        OrderEvent(
            event_type=EventType.ORDER_FILLED,
            order_id="123",
            symbol="EURUSD",
        )
    )

The bus is intentionally in-process. Distributed messaging can be added
later without changing the event definitions used by the engine.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from engine.events.event_types import Event, EventType

logger = logging.getLogger(__name__)


EventHandler = Callable[[Event], Any | Awaitable[Any]]


class EventBusError(RuntimeError):
    """Base exception for event-bus failures."""


class EventBusClosedError(EventBusError):
    """Raised when attempting to use a closed event bus."""


@dataclass(slots=True)
class EventDeliveryResult:
    """Result of delivering one event to one handler."""

    handler: str
    successful: bool
    error: str | None = None


@dataclass(slots=True)
class EventPublishResult:
    """Result of publishing an event."""

    event_id: str
    event_type: str
    delivered: int
    failed: int
    results: list[EventDeliveryResult]

    @property
    def successful(self) -> bool:
        """Return whether every handler completed successfully."""

        return self.failed == 0


class EventBus:
    """Asynchronous publish/subscribe event bus.

    The bus supports:

    - Multiple subscribers per event.
    - Async and synchronous handlers.
    - Wildcard subscriptions.
    - Handler-level failure isolation.
    - Subscription removal.
    - Graceful shutdown.
    - Optional concurrent event delivery.
    """

    WILDCARD = "*"

    def __init__(
        self,
        *,
        concurrent: bool = True,
        stop_on_handler_error: bool = False,
    ) -> None:
        self._subscribers: dict[
            EventType | str,
            list[EventHandler],
        ] = defaultdict(list)

        self._concurrent = concurrent
        self._stop_on_handler_error = stop_on_handler_error

        self._closed = False
        self._lock = asyncio.Lock()

        self._active_tasks: set[asyncio.Task[Any]] = set()

        self._published_events = 0
        self._delivered_events = 0
        self._failed_events = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_closed(self) -> bool:
        """Return whether the event bus is closed."""

        return self._closed

    @property
    def subscriber_count(self) -> int:
        """Return the total number of registered handlers."""

        return sum(len(handlers) for handlers in self._subscribers.values())

    @property
    def published_events(self) -> int:
        """Return the number of published events."""

        return self._published_events

    @property
    def delivered_events(self) -> int:
        """Return the number of successful handler deliveries."""

        return self._delivered_events

    @property
    def failed_events(self) -> int:
        """Return the number of failed handler deliveries."""

        return self._failed_events

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> None:
        """Subscribe a handler to an event type.

        A handler is only registered once for a given event type.

        Example:

            await bus.subscribe(
                EventType.ORDER_FILLED,
                portfolio.handle_order_filled,
            )
        """

        self._ensure_open()

        if not callable(handler):
            raise TypeError("Event handler must be callable.")

        normalized_type = _normalize_event_type(event_type)

        async with self._lock:
            handlers = self._subscribers[normalized_type]

            if handler not in handlers:
                handlers.append(handler)

        logger.debug(
            "Subscribed %s to %s.",
            _handler_name(handler),
            normalized_type,
        )

    async def unsubscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> bool:
        """Remove a handler from an event type.

        Returns:
            True if the handler was registered and removed.
        """

        normalized_type = _normalize_event_type(event_type)

        async with self._lock:
            handlers = self._subscribers.get(normalized_type)

            if not handlers:
                return False

            try:
                handlers.remove(handler)
            except ValueError:
                return False

            if not handlers:
                self._subscribers.pop(
                    normalized_type,
                    None,
                )

            return True

    async def unsubscribe_all(
        self,
        event_type: EventType | str | None = None,
    ) -> None:
        """Remove subscriptions.

        If ``event_type`` is omitted, all subscriptions are removed.
        """

        async with self._lock:
            if event_type is None:
                self._subscribers.clear()
                return

            normalized_type = _normalize_event_type(event_type)

            self._subscribers.pop(
                normalized_type,
                None,
            )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        event: Event,
    ) -> EventPublishResult:
        """Publish an event to all matching subscribers.

        Handler failures are isolated by default. One broken subscriber
        therefore does not prevent other subscribers from receiving the
        event.

        Args:
            event: AQE event to publish.

        Returns:
            Delivery information for the event.
        """

        self._ensure_open()

        if not isinstance(event, Event):
            raise TypeError("EventBus.publish() expects an Event instance.")

        self._published_events += 1

        handlers = await self._get_handlers(
            event.event_type,
        )

        if not handlers:
            logger.debug(
                "No subscribers registered for %s.",
                event.event_type,
            )

            return EventPublishResult(
                event_id=str(event.event_id),
                event_type=event.event_type.value,
                delivered=0,
                failed=0,
                results=[],
            )

        if self._concurrent:
            results = await self._publish_concurrent(
                event,
                handlers,
            )
        else:
            results = await self._publish_sequential(
                event,
                handlers,
            )

        delivered = sum(result.successful for result in results)

        failed = sum(not result.successful for result in results)

        self._delivered_events += delivered
        self._failed_events += failed

        return EventPublishResult(
            event_id=str(event.event_id),
            event_type=event.event_type.value,
            delivered=delivered,
            failed=failed,
            results=results,
        )

    async def _publish_concurrent(
        self,
        event: Event,
        handlers: list[EventHandler],
    ) -> list[EventDeliveryResult]:
        """Deliver an event to handlers concurrently."""

        tasks = [
            asyncio.create_task(
                self._deliver(
                    event,
                    handler,
                )
            )
            for handler in handlers
        ]

        self._track_tasks(tasks)

        return await asyncio.gather(*tasks)

    async def _publish_sequential(
        self,
        event: Event,
        handlers: list[EventHandler],
    ) -> list[EventDeliveryResult]:
        """Deliver an event to handlers sequentially."""

        results: list[EventDeliveryResult] = []

        for handler in handlers:
            result = await self._deliver(
                event,
                handler,
            )

            results.append(result)

            if not result.successful and self._stop_on_handler_error:
                break

        return results

    async def _deliver(
        self,
        event: Event,
        handler: EventHandler,
    ) -> EventDeliveryResult:
        """Deliver an event to one handler."""

        name = _handler_name(handler)

        try:
            result = handler(event)

            if inspect.isawaitable(result):
                await result

            logger.debug(
                "Delivered %s to %s.",
                event.event_type,
                name,
            )

            return EventDeliveryResult(
                handler=name,
                successful=True,
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "Event handler %s failed while processing %s.",
                name,
                event.event_type,
            )

            return EventDeliveryResult(
                handler=name,
                successful=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Handler lookup
    # ------------------------------------------------------------------

    async def _get_handlers(
        self,
        event_type: EventType,
    ) -> list[EventHandler]:
        """Return handlers for an event, including wildcard handlers."""

        async with self._lock:
            handlers = list(
                self._subscribers.get(
                    event_type,
                    (),
                )
            )

            wildcard_handlers = list(
                self._subscribers.get(
                    self.WILDCARD,
                    (),
                )
            )

        return handlers + wildcard_handlers

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def _track_tasks(
        self,
        tasks: list[asyncio.Task[Any]],
    ) -> None:
        """Track background tasks for shutdown coordination."""

        for task in tasks:
            self._active_tasks.add(task)

            task.add_done_callback(
                self._active_tasks.discard,
            )

    async def wait_for_handlers(self) -> None:
        """Wait for currently active event-handler tasks."""

        tasks = tuple(self._active_tasks)

        if not tasks:
            return

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the event bus.

        The in-process bus does not require external startup, but the
        method exists so it integrates cleanly with EngineLifecycle.
        """

        if self._closed:
            raise EventBusClosedError("Cannot start a closed event bus.")

        logger.info("AQE event bus started.")

    async def stop(self) -> None:
        """Stop the event bus gracefully."""

        if self._closed:
            return

        await self.wait_for_handlers()

        self._closed = True

        async with self._lock:
            self._subscribers.clear()

        logger.info("AQE event bus stopped.")

    async def close(self) -> None:
        """Alias for stop()."""

        await self.stop()

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def subscriptions(
        self,
    ) -> dict[str, int]:
        """Return subscription counts by event type."""

        async with self._lock:
            return {
                str(event_type): len(handlers)
                for event_type, handlers in self._subscribers.items()
            }

    def health(self) -> dict[str, Any]:
        """Return event-bus health information."""

        return {
            "status": "closed" if self._closed else "healthy",
            "closed": self._closed,
            "subscriber_count": self.subscriber_count,
            "published_events": self._published_events,
            "delivered_events": self._delivered_events,
            "failed_events": self._failed_events,
            "active_handlers": len(self._active_tasks),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        """Ensure the bus can accept operations."""

        if self._closed:
            raise EventBusClosedError("The AQE event bus has been closed.")


def _normalize_event_type(
    event_type: EventType | str,
) -> EventType | str:
    """Normalize event type values."""

    if isinstance(event_type, EventType):
        return event_type

    if event_type == EventBus.WILDCARD:
        return event_type

    try:
        return EventType(event_type)
    except ValueError as exc:
        raise ValueError(f"Unknown AQE event type: {event_type!r}") from exc


def _handler_name(
    handler: EventHandler,
) -> str:
    """Return a readable handler name."""

    if hasattr(handler, "__qualname__"):
        return str(handler.__qualname__)

    if hasattr(handler, "__name__"):
        return str(handler.__name__)

    return repr(handler)


__all__ = [
    "EventBus",
    "EventBusClosedError",
    "EventBusError",
    "EventDeliveryResult",
    "EventHandler",
    "EventPublishResult",
]
