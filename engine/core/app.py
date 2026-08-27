"""Application entry point for the Athena Quant Engine.

This module composes the AQE runtime:

    Settings
        ↓
    Dependencies
        ↓
    Lifecycle
        ↓
    Trading Loop

It intentionally does not contain strategy, risk, execution, broker, or
portfolio business logic.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from engine.core.dependency import (
    EngineDependencies,
    get_engine_dependencies,
    initialize_engine_dependencies,
    reset_engine_dependencies,
)
from engine.core.lifecycle import EngineLifecycle
from engine.core.settings import AQESettings, get_settings
from engine.core.trading_loop import TradingLoop

logger = logging.getLogger(__name__)


class EngineApplicationError(RuntimeError):
    """Base exception for AQE application failures."""


@dataclass
class AthenaQuantEngine:
    """Main AQE application runtime.

    The application owns the lifecycle and trading loop while dependencies
    are supplied through the dependency container.
    """

    settings: AQESettings = field(
        default_factory=get_settings,
    )

    dependencies: EngineDependencies | None = field(
        default=None,
        init=False,
    )

    lifecycle: EngineLifecycle | None = field(
        default=None,
        init=False,
    )

    trading_loop: TradingLoop | None = field(
        default=None,
        init=False,
    )

    _shutdown_requested: bool = field(
        default=False,
        init=False,
    )

    _initialized: bool = field(
        default=False,
        init=False,
    )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(
        self,
        **dependencies: Any,
    ) -> None:
        """Initialize AQE with its runtime dependencies.

        Dependencies are supplied here instead of being constructed inside
        the application. This keeps AQE testable and prevents the core
        application from becoming coupled to concrete implementations.
        """

        if self._initialized:
            raise EngineApplicationError(
                "Athena Quant Engine has already been initialized."
            )

        if dependencies:
            self.dependencies = initialize_engine_dependencies(
                **dependencies,
            )
        else:
            try:
                self.dependencies = get_engine_dependencies()
            except RuntimeError as exc:
                raise EngineApplicationError(
                    "No engine dependencies have been initialized."
                ) from exc

        self.lifecycle = EngineLifecycle(
            dependencies=self.dependencies,
        )

        self.trading_loop = TradingLoop(
            dependencies=self.dependencies,
            lifecycle=self.lifecycle,
        )

        self._register_callbacks()

        self._initialized = True

        logger.info("Athena Quant Engine initialized.")

    def _register_callbacks(self) -> None:
        """Register application-level lifecycle callbacks."""

        if self.lifecycle is None:
            return

        self.lifecycle.on(
            "startup",
            self._on_startup,
        )

        self.lifecycle.on(
            "running",
            self._on_running,
        )

        self.lifecycle.on(
            "pause",
            self._on_pause,
        )

        self.lifecycle.on(
            "resume",
            self._on_resume,
        )

        self.lifecycle.on(
            "shutdown",
            self._on_shutdown,
        )

        self.lifecycle.on(
            "failure",
            self._on_failure,
        )

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the AQE application."""

        self._require_initialized()

        if self.lifecycle is None:
            raise EngineApplicationError("Engine lifecycle is not available.")

        if self.trading_loop is None:
            raise EngineApplicationError("Trading loop is not available.")

        logger.info(
            "Starting %s v%s.",
            self.settings.app_name,
            self.settings.version,
        )

        await self.lifecycle.start()

        try:
            await self.trading_loop.start()

        except Exception:
            logger.exception("Failed to start AQE trading loop.")

            with suppress(Exception):
                await self.lifecycle.stop()

            raise

    # ------------------------------------------------------------------
    # Pause / resume
    # ------------------------------------------------------------------

    async def pause(self) -> None:
        """Pause trading without shutting down the engine."""

        self._require_initialized()

        if self.lifecycle is None:
            raise EngineApplicationError("Engine lifecycle is not available.")

        await self.lifecycle.pause()

    async def resume(self) -> None:
        """Resume trading after a pause."""

        self._require_initialized()

        if self.lifecycle is None:
            raise EngineApplicationError("Engine lifecycle is not available.")

        await self.lifecycle.resume()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Gracefully stop the AQE application."""

        if not self._initialized:
            return

        logger.info("Stopping Athena Quant Engine.")

        if self.trading_loop is not None:
            with suppress(Exception):
                await self.trading_loop.stop()

        if self.lifecycle is not None:
            with suppress(Exception):
                await self.lifecycle.stop()

        self._shutdown_requested = True

        logger.info("Athena Quant Engine stopped.")

    async def restart(self) -> None:
        """Restart the complete AQE application."""

        await self.stop()

        self._shutdown_requested = False

        if self.lifecycle is not None:
            self.lifecycle = EngineLifecycle(
                dependencies=self._require_dependencies(),
            )

        if self.trading_loop is not None:
            self.trading_loop = TradingLoop(
                dependencies=self._require_dependencies(),
                lifecycle=self._require_lifecycle(),
            )

        self._register_callbacks()

        await self.start()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run AQE until shutdown is requested."""

        self._require_initialized()

        await self.start()

        try:
            if self.lifecycle is None:
                raise EngineApplicationError("Engine lifecycle is not available.")

            await self.lifecycle.wait_for_shutdown()

        except asyncio.CancelledError:
            logger.info("AQE application task cancelled.")
            raise

        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def install_signal_handlers(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Install operating-system shutdown handlers.

        SIGINT is typically generated by Ctrl+C.
        SIGTERM is commonly used by Docker and production process managers.
        """

        loop = loop or asyncio.get_running_loop()

        for signum in (
            signal.SIGINT,
            signal.SIGTERM,
        ):
            with suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(
                    signum,
                    self.request_shutdown,
                )

    def request_shutdown(self) -> None:
        """Request graceful application shutdown."""

        if self._shutdown_requested:
            return

        self._shutdown_requested = True

        logger.info("AQE shutdown requested.")

        if self.lifecycle is not None:
            self.lifecycle.request_shutdown()

    # ------------------------------------------------------------------
    # Health / state
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Return the current engine state."""

        if self.lifecycle is None:
            return "uninitialized"

        return self.lifecycle.state.value

    @property
    def is_running(self) -> bool:
        """Return whether AQE is currently running."""

        return self.lifecycle is not None and self.lifecycle.is_running

    @property
    def is_paused(self) -> bool:
        """Return whether AQE is currently paused."""

        return self.lifecycle is not None and self.lifecycle.is_paused

    def health(self) -> dict[str, Any]:
        """Return a lightweight engine health snapshot."""

        lifecycle_snapshot = (
            self.lifecycle.snapshot() if self.lifecycle is not None else None
        )

        trading_stats = (
            self.trading_loop.stats.snapshot()
            if self.trading_loop is not None
            else None
        )

        return {
            "application": self.settings.app_name,
            "version": self.settings.version,
            "state": self.state,
            "initialized": self._initialized,
            "shutdown_requested": self._shutdown_requested,
            "lifecycle": (
                lifecycle_snapshot.__dict__
                if lifecycle_snapshot is not None
                and hasattr(lifecycle_snapshot, "__dict__")
                else lifecycle_snapshot
            ),
            "trading_loop": trading_stats,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def _on_startup(self) -> None:
        """Handle successful dependency startup."""

        logger.info("AQE dependencies started.")

    async def _on_running(self) -> None:
        """Handle transition to running state."""

        logger.info("AQE is now accepting trading cycles.")

    async def _on_pause(self) -> None:
        """Handle trading pause."""

        logger.warning("AQE trading has been paused.")

    async def _on_resume(self) -> None:
        """Handle trading resume."""

        logger.info("AQE trading has resumed.")

    async def _on_shutdown(self) -> None:
        """Handle lifecycle shutdown."""

        logger.info("AQE lifecycle shutdown initiated.")

    async def _on_failure(self) -> None:
        """Handle an engine lifecycle failure."""

        logger.error("AQE lifecycle failure detected.")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _require_initialized(self) -> None:
        """Ensure the application has been initialized."""

        if not self._initialized:
            raise EngineApplicationError(
                "Athena Quant Engine has not been initialized. "
                "Call initialize() before starting the engine."
            )

    def _require_dependencies(self) -> EngineDependencies:
        """Return initialized dependencies."""

        if self.dependencies is None:
            raise EngineApplicationError("Engine dependencies are not initialized.")

        return self.dependencies

    def _require_lifecycle(self) -> EngineLifecycle:
        """Return the current lifecycle."""

        if self.lifecycle is None:
            raise EngineApplicationError("Engine lifecycle is not initialized.")

        return self.lifecycle


# ----------------------------------------------------------------------
# Application factory
# ----------------------------------------------------------------------


def create_engine(
    settings: AQESettings | None = None,
    **dependencies: Any,
) -> AthenaQuantEngine:
    """Create and initialize an AQE application.

    Example:

        engine = create_engine(
            settings=settings,
            database=database,
            event_bus=event_bus,
            broker_manager=broker_manager,
            market_feed=market_feed,
            strategy_manager=strategy_manager,
            risk_manager=risk_manager,
            execution_engine=execution_engine,
            portfolio_manager=portfolio_manager,
        )
    """

    application = AthenaQuantEngine(
        settings=settings or get_settings(),
    )

    application.initialize(
        **dependencies,
    )

    return application


# ----------------------------------------------------------------------
# Default process entry point
# ----------------------------------------------------------------------


async def main() -> None:
    """Run the default AQE application."""

    application = create_engine()

    application.install_signal_handlers()

    await application.run()


def run() -> None:
    """Synchronous process entry point."""

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("AQE terminated by keyboard interrupt.")


__all__ = [
    "AthenaQuantEngine",
    "EngineApplicationError",
    "create_engine",
    "main",
    "run",
]
