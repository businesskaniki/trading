"""Main trading loop for the Athena Quant Engine.

The trading loop coordinates the high-level live trading workflow:

    Market Data
        ↓
    Strategy
        ↓
    Risk
        ↓
    Execution
        ↓
    Portfolio
        ↓
    Events / Analytics

The loop itself should remain an orchestrator. Business rules belong to
the individual engine subsystems.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from engine.core.constants import EngineState
from engine.core.dependency import EngineDependencies
from engine.core.lifecycle import EngineLifecycle

logger = logging.getLogger(__name__)


class TradingLoopError(RuntimeError):
    """Base exception for trading-loop failures."""


class TradingLoopStopped(TradingLoopError):
    """Raised when the trading loop is stopped."""


TradingCycleCallback = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(slots=True)
class TradingLoopStats:
    """Runtime statistics for the trading loop."""

    cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0

    last_cycle_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None

    last_cycle_duration_seconds: float | None = None
    average_cycle_duration_seconds: float = 0.0

    consecutive_failures: int = 0
    max_consecutive_failures: int = 0

    started_at: datetime | None = None
    stopped_at: datetime | None = None

    def record_success(
        self,
        duration_seconds: float,
    ) -> None:
        """Record a successful trading cycle."""

        self.cycles += 1
        self.successful_cycles += 1
        self.consecutive_failures = 0

        now = _utc_now()

        self.last_cycle_at = now
        self.last_success_at = now
        self.last_cycle_duration_seconds = duration_seconds

        self.average_cycle_duration_seconds = _rolling_average(
            self.average_cycle_duration_seconds,
            duration_seconds,
            self.successful_cycles,
        )

    def record_failure(
        self,
        duration_seconds: float,
    ) -> None:
        """Record a failed trading cycle."""

        self.cycles += 1
        self.failed_cycles += 1
        self.consecutive_failures += 1

        self.max_consecutive_failures = max(
            self.max_consecutive_failures,
            self.consecutive_failures,
        )

        now = _utc_now()

        self.last_cycle_at = now
        self.last_failure_at = now
        self.last_cycle_duration_seconds = duration_seconds

    def snapshot(self) -> dict[str, Any]:
        """Return serializable loop statistics."""

        return {
            "cycles": self.cycles,
            "successful_cycles": self.successful_cycles,
            "failed_cycles": self.failed_cycles,
            "last_cycle_at": self.last_cycle_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_cycle_duration_seconds": (self.last_cycle_duration_seconds),
            "average_cycle_duration_seconds": (self.average_cycle_duration_seconds),
            "consecutive_failures": self.consecutive_failures,
            "max_consecutive_failures": self.max_consecutive_failures,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }


@dataclass
class TradingLoop:
    """Coordinate the AQE live trading cycle."""

    dependencies: EngineDependencies
    lifecycle: EngineLifecycle

    _running: bool = field(
        default=False,
        init=False,
    )

    _task: asyncio.Task[None] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    _stop_event: asyncio.Event | None = field(
        default=None,
        init=False,
        repr=False,
    )

    _wake_event: asyncio.Event | None = field(
        default=None,
        init=False,
        repr=False,
    )

    _stats: TradingLoopStats = field(
        default_factory=TradingLoopStats,
        init=False,
    )

    _callbacks: list[TradingCycleCallback] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    _failure_threshold: int = field(
        default=5,
        init=False,
    )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return whether the trading loop is currently running."""

        return self._running

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Return the underlying asyncio task."""

        return self._task

    @property
    def stats(self) -> TradingLoopStats:
        """Return current trading-loop statistics."""

        return self._stats

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        failure_threshold: int | None = None,
    ) -> None:
        """Configure runtime safety behavior."""

        if failure_threshold is not None:
            if failure_threshold < 1:
                raise ValueError("failure_threshold must be greater than zero.")

            self._failure_threshold = failure_threshold

    def on_cycle(
        self,
        callback: TradingCycleCallback,
    ) -> None:
        """Register a callback executed after each completed cycle."""

        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the trading loop as a background task."""

        if self._running:
            return

        if self.lifecycle.state != EngineState.RUNNING:
            raise TradingLoopError(
                "The engine lifecycle must be RUNNING before "
                "starting the trading loop."
            )

        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()

        self._stats.started_at = _utc_now()
        self._stats.stopped_at = None

        self._running = True

        self._task = asyncio.create_task(
            self._run(),
            name="aqe-trading-loop",
        )

        logger.info("AQE trading loop started.")

    async def stop(self) -> None:
        """Stop the trading loop gracefully."""

        if not self._running:
            return

        logger.info("Stopping AQE trading loop.")

        self._running = False

        if self._stop_event is not None:
            self._stop_event.set()

        if self._wake_event is not None:
            self._wake_event.set()

        task = self._task

        if task is not None:
            with suppress(asyncio.CancelledError):
                await task

        self._task = None
        self._stats.stopped_at = _utc_now()

        logger.info("AQE trading loop stopped.")

    async def restart(self) -> None:
        """Restart the trading loop."""

        await self.stop()
        await self.start()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Run the continuous trading cycle."""

        interval = self.dependencies.settings.runtime.tick_interval_seconds

        while self._running:
            if self._stop_requested():
                break

            try:
                await self.lifecycle.wait_until_resumed()

                if not self._running:
                    break

                if self.lifecycle.state != EngineState.RUNNING:
                    await self._wait_for_next_iteration(interval)
                    continue

                cycle_started = time.perf_counter()

                context = await self._run_cycle()

                duration = time.perf_counter() - cycle_started

                self._stats.record_success(duration)

                await self._emit_cycle(context)

            except asyncio.CancelledError:
                logger.debug("AQE trading loop task cancelled.")
                raise

            except Exception as exc:
                duration = (
                    time.perf_counter() - cycle_started
                    if "cycle_started" in locals()
                    else 0.0
                )

                self._stats.record_failure(duration)

                logger.exception(
                    "Trading cycle failed: %s",
                    exc,
                )

                await self._handle_cycle_failure(exc)

            finally:
                await self._wait_for_next_iteration(interval)

    # ------------------------------------------------------------------
    # Trading cycle
    # ------------------------------------------------------------------

    async def _run_cycle(self) -> dict[str, Any]:
        """Execute one complete trading cycle.

        The exact implementation of each subsystem is intentionally
        delegated to that subsystem. This method only coordinates them.
        """

        timestamp = _utc_now()

        context: dict[str, Any] = {
            "timestamp": timestamp,
            "engine_state": self.lifecycle.state.value,
        }

        # --------------------------------------------------------------
        # 1. Market data
        # --------------------------------------------------------------

        market_data = await self._get_market_data()

        context["market_data"] = market_data

        # --------------------------------------------------------------
        # 2. Strategy
        # --------------------------------------------------------------

        signals = await self._generate_signals(
            market_data=market_data,
            context=context,
        )

        context["signals"] = signals

        # --------------------------------------------------------------
        # 3. Risk
        # --------------------------------------------------------------

        approved_signals = await self._validate_risk(
            signals=signals,
            context=context,
        )

        context["approved_signals"] = approved_signals

        # --------------------------------------------------------------
        # 4. Execution
        # --------------------------------------------------------------

        execution_results = await self._execute(
            signals=approved_signals,
            context=context,
        )

        context["execution_results"] = execution_results

        # --------------------------------------------------------------
        # 5. Portfolio
        # --------------------------------------------------------------

        portfolio_state = await self._update_portfolio(
            execution_results=execution_results,
            context=context,
        )

        context["portfolio"] = portfolio_state

        # --------------------------------------------------------------
        # 6. Events
        # --------------------------------------------------------------

        await self._publish_cycle_event(context)

        return context

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def _get_market_data(self) -> Any:
        """Retrieve the latest market data."""

        feed = self.dependencies.market_feed

        if feed is None:
            raise TradingLoopError("Market feed dependency is not configured.")

        method = _find_method(
            feed,
            (
                "get_latest",
                "get_market_data",
                "fetch",
                "update",
                "poll",
            ),
        )

        if method is None:
            raise TradingLoopError(
                "Market feed does not expose a supported data method."
            )

        return await _call(method)

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    async def _generate_signals(
        self,
        *,
        market_data: Any,
        context: dict[str, Any],
    ) -> Any:
        """Generate strategy signals."""

        strategy_manager = self.dependencies.strategy_manager

        if strategy_manager is None:
            raise TradingLoopError("Strategy manager dependency is not configured.")

        method = _find_method(
            strategy_manager,
            (
                "generate_signals",
                "evaluate",
                "run",
                "process",
            ),
        )

        if method is None:
            raise TradingLoopError(
                "Strategy manager does not expose a supported "
                "signal-generation method."
            )

        return await _call(
            method,
            market_data=market_data,
            context=context,
        )

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------

    async def _validate_risk(
        self,
        *,
        signals: Any,
        context: dict[str, Any],
    ) -> Any:
        """Validate strategy signals through the risk subsystem."""

        risk_manager = self.dependencies.risk_manager

        if risk_manager is None:
            raise TradingLoopError("Risk manager dependency is not configured.")

        method = _find_method(
            risk_manager,
            (
                "validate_signals",
                "validate",
                "check",
                "evaluate",
            ),
        )

        if method is None:
            raise TradingLoopError(
                "Risk manager does not expose a supported validation method."
            )

        return await _call(
            method,
            signals=signals,
            context=context,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        *,
        signals: Any,
        context: dict[str, Any],
    ) -> Any:
        """Execute approved trading signals."""

        execution_engine = self.dependencies.execution_engine

        if execution_engine is None:
            raise TradingLoopError("Execution engine dependency is not configured.")

        method = _find_method(
            execution_engine,
            (
                "execute_signals",
                "execute",
                "process",
                "submit",
            ),
        )

        if method is None:
            raise TradingLoopError(
                "Execution engine does not expose a supported execution method."
            )

        return await _call(
            method,
            signals=signals,
            context=context,
        )

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def _update_portfolio(
        self,
        *,
        execution_results: Any,
        context: dict[str, Any],
    ) -> Any:
        """Update portfolio/account state after execution."""

        portfolio_manager = self.dependencies.portfolio_manager

        if portfolio_manager is None:
            raise TradingLoopError("Portfolio manager dependency is not configured.")

        method = _find_method(
            portfolio_manager,
            (
                "process_execution_results",
                "update",
                "refresh",
                "sync",
            ),
        )

        if method is None:
            raise TradingLoopError(
                "Portfolio manager does not expose a supported "
                "portfolio update method."
            )

        return await _call(
            method,
            execution_results=execution_results,
            context=context,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def _publish_cycle_event(
        self,
        context: dict[str, Any],
    ) -> None:
        """Publish a trading-cycle event when an event bus is available."""

        event_bus = self.dependencies.event_bus

        if event_bus is None:
            return

        method = _find_method(
            event_bus,
            (
                "publish",
                "emit",
                "dispatch",
            ),
        )

        if method is None:
            return

        event = {
            "type": "trading_cycle_completed",
            "timestamp": context["timestamp"],
            "data": context,
        }

        await _call(
            method,
            event,
        )

    async def _emit_cycle(
        self,
        context: dict[str, Any],
    ) -> None:
        """Execute registered cycle callbacks."""

        for callback in tuple(self._callbacks):
            try:
                result = callback(context)

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception("Trading-cycle callback failed.")

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    async def _handle_cycle_failure(
        self,
        error: Exception,
    ) -> None:
        """Handle repeated trading-cycle failures safely."""

        if self._stats.consecutive_failures >= self._failure_threshold:
            logger.critical(
                "AQE trading loop reached the consecutive failure "
                "threshold (%d). Pausing trading.",
                self._failure_threshold,
            )

            with suppress(Exception):
                await self.lifecycle.pause()

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    async def _wait_for_next_iteration(
        self,
        interval: float,
    ) -> None:
        """Wait before beginning the next trading cycle."""

        if not self._running:
            return

        if self._stop_event is None:
            return

        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=max(interval, 0.01),
            )
        except asyncio.TimeoutError:
            return

    def _stop_requested(self) -> bool:
        """Return whether loop shutdown has been requested."""

        if not self._running:
            return True

        if self._stop_event is None:
            return False

        return self._stop_event.is_set()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _find_method(
    resource: Any,
    method_names: tuple[str, ...],
) -> Callable[..., Any] | None:
    """Find the first available callable method."""

    for name in method_names:
        method = getattr(resource, name, None)

        if callable(method):
            return method

    return None


async def _call(
    method: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Call either synchronous or asynchronous methods."""

    result = method(*args, **kwargs)

    if inspect.isawaitable(result):
        return await result

    return result


def _rolling_average(
    current_average: float,
    value: float,
    count: int,
) -> float:
    """Calculate a numerically stable incremental average."""

    if count <= 1:
        return value

    return current_average + (value - current_average) / count


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


__all__ = [
    "TradingLoop",
    "TradingLoopError",
    "TradingLoopStats",
    "TradingLoopStopped",
]
