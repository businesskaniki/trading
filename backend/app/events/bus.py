from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .base import Event

logger = logging.getLogger(__name__)

EventHandler = Callable[[Event], Any]

E = TypeVar("E", bound=Event)


class EventBusError(Exception):
    """Base exception for Event Bus failures."""

    pass


class EventBus:
    """
    In-process asynchronous event bus for AQE.

    Responsibilities:
        - Register event handlers.
        - Remove event handlers.
        - Publish events.
        - Deliver events to matching subscribers.

    The Event Bus intentionally contains no trading-specific logic.
    """

    def __init__(self) -> None:
        self._handlers: dict[
            type[Event],
            list[EventHandler],
        ] = defaultdict(list)

        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # SUBSCRIBE
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], Any],
    ) -> None:
        """
        Register a handler for an event type.

        A handler may be synchronous or asynchronous.
        """

        if not inspect.isclass(event_type):
            raise EventBusError("event_type must be an Event class.")

        if not issubclass(event_type, Event):
            raise EventBusError("event_type must inherit from Event.")

        if not callable(handler):
            raise EventBusError("Event handler must be callable.")

        async with self._lock:
            handlers = self._handlers[event_type]

            if handler not in handlers:
                handlers.append(handler)

    # ------------------------------------------------------------------
    # UNSUBSCRIBE
    # ------------------------------------------------------------------

    async def unsubscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], Any],
    ) -> None:
        """
        Remove a previously registered event handler.
        """

        async with self._lock:
            handlers = self._handlers.get(event_type)

            if not handlers:
                return

            if handler in handlers:
                handlers.remove(handler)

            if not handlers:
                self._handlers.pop(event_type, None)

    # ------------------------------------------------------------------
    # PUBLISH
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all handlers registered for its exact type.

        Handlers are executed asynchronously.

        A failure in one handler is logged without preventing the
        remaining handlers from receiving the event.
        """

        if not isinstance(event, Event):
            raise EventBusError("Only Event instances can be published.")

        async with self._lock:
            handlers = list(self._handlers.get(type(event), []))

        if not handlers:
            return

        for handler in handlers:
            try:
                result = handler(event)

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception(
                    "Event handler failed. " "event_type=%s handler=%s event_id=%s",
                    type(event).__name__,
                    getattr(handler, "__name__", repr(handler)),
                    event.event_id,
                )

    # ------------------------------------------------------------------
    # PUBLISH CONCURRENTLY
    # ------------------------------------------------------------------

    async def publish_concurrent(
        self,
        event: Event,
    ) -> None:
        """
        Publish an event to all matching handlers concurrently.

        This method is useful when handlers are independent and should
        not block one another.

        Handler failures are isolated and logged.
        """

        if not isinstance(event, Event):
            raise EventBusError("Only Event instances can be published.")

        async with self._lock:
            handlers = list(self._handlers.get(type(event), []))

        if not handlers:
            return

        async def execute_handler(
            handler: EventHandler,
        ) -> None:
            try:
                result = handler(event)

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception(
                    "Concurrent event handler failed. "
                    "event_type=%s handler=%s event_id=%s",
                    type(event).__name__,
                    getattr(handler, "__name__", repr(handler)),
                    event.event_id,
                )

        await asyncio.gather(*(execute_handler(handler) for handler in handlers))

    # ------------------------------------------------------------------
    # INSPECTION
    # ------------------------------------------------------------------

    async def handler_count(
        self,
        event_type: type[Event],
    ) -> int:
        """
        Return the number of handlers registered for an event type.
        """

        async with self._lock:
            return len(self._handlers.get(event_type, []))

    async def clear(self) -> None:
        """
        Remove all registered handlers.

        Primarily useful for application shutdown and testing.
        """

        async with self._lock:
            self._handlers.clear()


event_bus = EventBus()
