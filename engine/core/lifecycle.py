"""Lifecycle management for the Athena Quant Engine.

The lifecycle manager owns the runtime state transitions of AQE and
coordinates startup, pause/resume, and shutdown of engine dependencies.

Business logic belongs in the individual engine subsystems, not here.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Awaitable, Callable

from engine.core.constants import EngineState
from engine.core.dependency import EngineDependencies

logger = logging.getLogger(__name__)


class LifecycleError(RuntimeError):
    """Base exception for engine lifecycle failures."""


class InvalidStateTransition(LifecycleError):
    """Raised when an invalid engine state transition is requested."""


class StartupError(LifecycleError):
    """Raised when engine startup fails."""


class ShutdownError(LifecycleError):
    """Raised when engine shutdown fails."""


LifecycleCallback = Callable[[], Any | Awaitable[Any]]


@dataclass(slots=True)
class LifecycleSnapshot:
    """Immutable-style snapshot of the engine lifecycle state."""

    state: EngineState
    started_at: datetime | None
    stopped_at: datetime | None
    last_error: str | None
    startup_duration_seconds: float | None
    shutdown_duration_seconds: float | None


@dataclass
class EngineLifecycle:
    """Manage the lifecycle of the Athena Quant Engine."""

    dependencies: EngineDependencies

    _state: EngineState = field(
        default=EngineState.CREATED,
        init=False,
    )

    _started_at: datetime | None = field(
        default=None,
        init=False,
    )

    _stopped_at: datetime | None = field(
        default=None,
        init=False,
    )

    _last_error: str | None = field(
        default=None,
        init=False,
    )

    _startup_duration_seconds: float | None = field(
        default=None,
        init=False,
    )

    _shutdown_duration_seconds: float | None = field(
        default=None,
        init=False,
    )

    _lock: RLock = field(
        default_factory=RLock,
        init=False,
        repr=False,
    )

    _pause_event: asyncio.Event | None = field(
        default=None,
        init=False,
        repr=False,
    )

    _shutdown_event: asyncio.Event | None = field(
        default=None,
        init=False,
        repr=False,
    )

    _callbacks: dict[str, list[LifecycleCallback]] = field(
        default_factory=lambda: {
            "startup": [],
            "running": [],
            "pause": [],
            "resume": [],
            "shutdown": [],
            "failure": [],
        },
        init=False,
        repr=False,
    )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> EngineState:
        """Return the current engine state."""

        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        """Return whether the engine is actively running."""

        return self.state == EngineState.RUNNING

    @property
    def is_paused(self) -> bool:
        """Return whether the engine is paused."""

        return self.state == EngineState.PAUSED

    @property
    def is_stopped(self) -> bool:
        """Return whether the engine is stopped."""

        return self.state == EngineState.STOPPED

    @property
    def is_failed(self) -> bool:
        """Return whether the engine has failed."""

        return self.state == EngineState.FAILED

    def snapshot(self) -> LifecycleSnapshot:
        """Return the current lifecycle state as a snapshot."""

        with self._lock:
            return LifecycleSnapshot(
                state=self._state,
                started_at=self._started_at,
                stopped_at=self._stopped_at,
                last_error=self._last_error,
                startup_duration_seconds=self._startup_duration_seconds,
                shutdown_duration_seconds=self._shutdown_duration_seconds,
            )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on(
        self,
        event: str,
        callback: LifecycleCallback,
    ) -> None:
        """Register a lifecycle callback."""

        if event not in self._callbacks:
            raise ValueError(
                f"Unknown lifecycle event '{event}'. "
                f"Supported events: {sorted(self._callbacks)}"
            )

        self._callbacks[event].append(callback)

    async def _emit(
        self,
        event: str,
    ) -> None:
        """Execute registered lifecycle callbacks."""

        callbacks = tuple(self._callbacks.get(event, ()))

        for callback in callbacks:
            result = callback()

            if inspect.isawaitable(result):
                await result

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the AQE runtime.

        Startup is intentionally fail-closed. If dependency validation or
        startup fails, the engine transitions to FAILED and attempts to
        clean up resources that were already started.
        """

        with self._lock:
            if self._state == EngineState.RUNNING:
                return

            if self._state == EngineState.STARTING:
                raise LifecycleError("AQE startup is already in progress.")

            if self._state in {
                EngineState.PAUSING,
                EngineState.STOPPING,
            }:
                raise InvalidStateTransition(
                    f"Cannot start AQE while state is '{self._state}'."
                )

            self._state = EngineState.STARTING
            self._last_error = None

        start_time = asyncio.get_running_loop().time()

        try:
            logger.info("Starting Athena Quant Engine.")

            self.dependencies.validate()

            await self._start_dependencies()

            self._pause_event = asyncio.Event()
            self._pause_event.set()

            self._shutdown_event = asyncio.Event()

            with self._lock:
                self._started_at = _utc_now()
                self._stopped_at = None
                self._startup_duration_seconds = (
                    asyncio.get_running_loop().time() - start_time
                )
                self._state = EngineState.RUNNING

            await self._emit("startup")
            await self._emit("running")

            logger.info("Athena Quant Engine started successfully.")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._state = EngineState.FAILED

            logger.exception("Athena Quant Engine startup failed.")

            with suppress(Exception):
                await self._stop_dependencies()

            await self._emit_failure(exc)

            raise StartupError("Athena Quant Engine failed to start.") from exc

    async def _start_dependencies(self) -> None:
        """Start dependencies while supporting sync and async methods."""

        resources = (
            self.dependencies.database,
            self.dependencies.redis,
            self.dependencies.event_bus,
            self.dependencies.market_feed,
            self.dependencies.broker_manager,
            self.dependencies.strategy_manager,
            self.dependencies.risk_manager,
            self.dependencies.execution_engine,
            self.dependencies.portfolio_manager,
            self.dependencies.analytics,
            self.dependencies.monitoring,
            self.dependencies.ml_engine,
        )

        started: list[Any] = []

        try:
            for resource in resources:
                if resource is None:
                    continue

                await _call_lifecycle_method(
                    resource,
                    "start",
                )

                started.append(resource)

        except Exception:
            for resource in reversed(started):
                with suppress(Exception):
                    await _call_lifecycle_method(
                        resource,
                        "stop",
                    )

            raise

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    async def pause(self) -> None:
        """Pause trading activity without shutting down the engine."""

        with self._lock:
            if self._state == EngineState.PAUSED:
                return

            if self._state != EngineState.RUNNING:
                raise InvalidStateTransition(
                    f"Cannot pause AQE while state is '{self._state}'."
                )

            self._state = EngineState.PAUSING

        try:
            logger.info("Pausing Athena Quant Engine.")

            await self._emit("pause")

            if self._pause_event is not None:
                self._pause_event.clear()

            with self._lock:
                self._state = EngineState.PAUSED

            logger.info("Athena Quant Engine is paused.")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._state = EngineState.FAILED

            await self._emit_failure(exc)

            raise LifecycleError("Failed to pause Athena Quant Engine.") from exc

    async def resume(self) -> None:
        """Resume trading activity after a pause."""

        with self._lock:
            if self._state == EngineState.RUNNING:
                return

            if self._state != EngineState.PAUSED:
                raise InvalidStateTransition(
                    f"Cannot resume AQE while state is '{self._state}'."
                )

            if self._shutdown_event is not None:
                if self._shutdown_event.is_set():
                    raise InvalidStateTransition(
                        "Cannot resume AQE because shutdown was requested."
                    )

            if self._pause_event is not None:
                self._pause_event.set()

            self._state = EngineState.RUNNING

        try:
            await self._emit("resume")

            logger.info("Athena Quant Engine resumed.")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._state = EngineState.FAILED

            await self._emit_failure(exc)

            raise LifecycleError("Failed to resume Athena Quant Engine.") from exc

    async def wait_until_resumed(self) -> None:
        """Block until the engine is in an active trading state."""

        if self._pause_event is None:
            raise LifecycleError("Engine lifecycle has not been started.")

        await self._pause_event.wait()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Stop the AQE runtime and release its dependencies."""

        with self._lock:
            if self._state == EngineState.STOPPED:
                return

            if self._state == EngineState.CREATED:
                self._state = EngineState.STOPPED
                self._stopped_at = _utc_now()
                return

            if self._state == EngineState.STOPPING:
                return

            self._state = EngineState.STOPPING

        start_time = asyncio.get_running_loop().time()

        try:
            logger.info("Stopping Athena Quant Engine.")

            if self._shutdown_event is not None:
                self._shutdown_event.set()

            if self._pause_event is not None:
                self._pause_event.set()

            await self._emit("shutdown")

            await self._stop_dependencies()

            with self._lock:
                self._stopped_at = _utc_now()
                self._shutdown_duration_seconds = (
                    asyncio.get_running_loop().time() - start_time
                )
                self._state = EngineState.STOPPED

            logger.info("Athena Quant Engine stopped successfully.")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._state = EngineState.FAILED
                self._shutdown_duration_seconds = (
                    asyncio.get_running_loop().time() - start_time
                )

            logger.exception("Athena Quant Engine shutdown failed.")

            await self._emit_failure(exc)

            raise ShutdownError(
                "Athena Quant Engine failed to shut down cleanly."
            ) from exc

    async def _stop_dependencies(self) -> None:
        """Stop dependencies in reverse startup order."""

        resources = (
            self.dependencies.ml_engine,
            self.dependencies.monitoring,
            self.dependencies.analytics,
            self.dependencies.portfolio_manager,
            self.dependencies.execution_engine,
            self.dependencies.risk_manager,
            self.dependencies.strategy_manager,
            self.dependencies.broker_manager,
            self.dependencies.market_feed,
            self.dependencies.event_bus,
            self.dependencies.redis,
            self.dependencies.database,
        )

        errors: list[Exception] = []

        for resource in resources:
            if resource is None:
                continue

            try:
                await _call_lifecycle_method(
                    resource,
                    "stop",
                )

            except Exception as exc:
                errors.append(exc)

                logger.exception(
                    "Failed to stop AQE dependency: %r",
                    resource,
                )

        if errors:
            raise ShutdownError(
                f"{len(errors)} AQE dependency shutdown operation(s) failed."
            ) from errors[0]

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    async def _emit_failure(
        self,
        error: Exception,
    ) -> None:
        """Notify registered failure callbacks."""

        callbacks = tuple(self._callbacks.get("failure", ()))

        for callback in callbacks:
            try:
                result = callback()

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception("AQE lifecycle failure callback failed.")

    # ------------------------------------------------------------------
    # Shutdown coordination
    # ------------------------------------------------------------------

    async def wait_for_shutdown(self) -> None:
        """Wait until the engine receives a shutdown request."""

        if self._shutdown_event is None:
            raise LifecycleError("Engine lifecycle has not been started.")

        await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        """Request shutdown without immediately stopping dependencies."""

        if self._shutdown_event is None:
            return

        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> EngineLifecycle:
        """Start the engine when entering an async context."""

        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Stop the engine when leaving an async context."""

        await self.stop()


async def _call_lifecycle_method(
    resource: Any,
    method_name: str,
) -> None:
    """Call a lifecycle method on either sync or async resources."""

    method = getattr(resource, method_name, None)

    if method is None:
        return

    result = method()

    if inspect.isawaitable(result):
        await result


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


__all__ = [
    "EngineLifecycle",
    "InvalidStateTransition",
    "LifecycleError",
    "LifecycleSnapshot",
    "ShutdownError",
    "StartupError",
]
