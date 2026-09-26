from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from .engine import BacktestConfig, BacktestEngine, BacktestStatus
from .orchestration import BacktestOrchestrationResult, BacktestOrchestrator

BacktestOrchestratorFactory = Callable[
    [BacktestConfig],
    BacktestOrchestrator | Awaitable[BacktestOrchestrator],
]


@dataclass(slots=True)
class ManagedBacktest:
    """
    Application-level state for one backtest run.

    The actual simulation state remains owned by BacktestEngine.
    This object only manages lifecycle/task ownership around it.
    """

    backtest_id: UUID
    config: BacktestConfig
    orchestrator: BacktestOrchestrator
    task: asyncio.Task[BacktestOrchestrationResult] | None = None
    result: BacktestOrchestrationResult | None = None
    error: str | None = None

    @property
    def engine(self) -> BacktestEngine:
        return self.orchestrator.engine

    @property
    def status(self) -> BacktestStatus:
        return self.engine.run.status

    @property
    def running(self) -> bool:
        return (
            self.task is not None
            and not self.task.done()
            and self.status == BacktestStatus.RUNNING
        )


class BacktestService:
    """
    Application service responsible for backtest lifecycle.

    BacktestEngine owns simulation mechanics.

    BacktestOrchestrator owns:
        strategy -> signal -> risk -> execution -> backtest engine

    BacktestService owns:
        API-level lifecycle
        background task management
        run registration
        status/result exposure

    No persistence is performed here. The initial implementation is
    intentionally in-memory; database persistence can be added above
    or alongside this service later without changing BacktestEngine.
    """

    def __init__(
        self,
        orchestrator_factory: BacktestOrchestratorFactory,
    ) -> None:
        self._orchestrator_factory = orchestrator_factory
        self._runs: dict[UUID, ManagedBacktest] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        config: BacktestConfig,
    ) -> dict:
        """
        Create and register a backtest without starting it.

        The returned backtest remains in CREATED state until start()
        is explicitly called.
        """
        orchestrator = await self._build_orchestrator(config)
        engine = orchestrator.engine
        backtest_id = engine.run.run_id

        managed = ManagedBacktest(
            backtest_id=backtest_id,
            config=config,
            orchestrator=orchestrator,
        )

        async with self._lock:
            if backtest_id in self._runs:
                raise RuntimeError(f"Backtest {backtest_id} is already registered.")

            self._runs[backtest_id] = managed

        return self.snapshot(backtest_id)

    async def start(
        self,
        backtest_id: UUID,
    ) -> dict:
        """
        Start a registered backtest in the background.

        The HTTP/API caller does not wait for the entire backtest to
        finish. The returned snapshot describes the current state.
        """
        managed = await self._get_managed(backtest_id)

        if managed.task is not None and not managed.task.done():
            raise RuntimeError(f"Backtest {backtest_id} is already running.")

        if managed.status != BacktestStatus.CREATED:
            raise RuntimeError(
                f"Backtest {backtest_id} cannot be started from "
                f"state {managed.status.value}."
            )

        managed.task = asyncio.create_task(
            self._run(managed),
            name=f"aqe-backtest-{backtest_id}",
        )

        return self.snapshot(backtest_id)

    async def stop(
        self,
        backtest_id: UUID,
    ) -> dict:
        """
        Request cooperative shutdown of a running backtest.

        BacktestEngine.stop() changes the simulation state to STOPPED.
        BacktestEngine.run_backtest() observes that state between events
        and exits cleanly.
        """
        managed = await self._get_managed(backtest_id)

        if managed.task is None or managed.task.done():
            if managed.status == BacktestStatus.CREATED:
                raise RuntimeError(f"Backtest {backtest_id} has not been started.")

            return self.snapshot(backtest_id)

        if managed.status == BacktestStatus.RUNNING:
            managed.engine.stop()

        return self.snapshot(backtest_id)

    async def get(
        self,
        backtest_id: UUID,
    ) -> dict:
        """
        Return the current API-facing state of a backtest.
        """
        await self._get_managed(backtest_id)
        return self.snapshot(backtest_id)

    async def list(self) -> list[dict]:
        """
        Return all registered backtests.

        Newest runs are returned first.
        """
        async with self._lock:
            runs = list(self._runs.values())

        runs.sort(
            key=lambda item: (
                item.engine.run.started_at or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )

        return [self._snapshot(managed) for managed in runs]

    async def remove(
        self,
        backtest_id: UUID,
    ) -> None:
        """
        Remove a completed/stopped/failed backtest from the in-memory
        registry.

        Running backtests cannot be removed.
        """
        managed = await self._get_managed(backtest_id)

        if managed.task is not None and not managed.task.done():
            raise RuntimeError(f"Backtest {backtest_id} is still running.")

        async with self._lock:
            self._runs.pop(backtest_id, None)

    async def stop_all(self) -> None:
        """
        Request cooperative shutdown of all currently running
        backtests.

        This is intended for application shutdown.
        """
        async with self._lock:
            runs = list(self._runs.values())

        running = [
            managed
            for managed in runs
            if (
                managed.task is not None
                and not managed.task.done()
                and managed.status == BacktestStatus.RUNNING
            )
        ]

        for managed in running:
            managed.engine.stop()

        tasks = [managed.task for managed in running if managed.task is not None]

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    def snapshot(
        self,
        backtest_id: UUID,
    ) -> dict:
        """
        Synchronous snapshot helper.

        This is intentionally separate from get() so internal code and
        API serialization can obtain a snapshot without another lookup.
        """
        managed = self._runs.get(backtest_id)

        if managed is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        return self._snapshot(managed)

    async def _run(
        self,
        managed: ManagedBacktest,
    ) -> BacktestOrchestrationResult | None:
        """
        Execute one orchestrator and capture its terminal state.

        Exceptions are captured into ManagedBacktest rather than being
        allowed to become unobserved asyncio task exceptions.
        """
        try:
            result = await managed.orchestrator.run()
            managed.result = result
            return result

        except asyncio.CancelledError:
            managed.error = "Backtest task was cancelled."
            raise

        except Exception as exc:
            managed.error = str(exc)

            if managed.engine.run.status != BacktestStatus.FAILED:
                managed.engine.run.status = BacktestStatus.FAILED
                managed.engine.run.errors.append(str(exc))

            return None

    async def _build_orchestrator(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Resolve either a synchronous or asynchronous orchestrator factory.
        """
        result = self._orchestrator_factory(config)

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(result, BacktestOrchestrator):
            raise TypeError(
                "Backtest orchestrator factory must return " "BacktestOrchestrator."
            )

        return result

    async def _get_managed(
        self,
        backtest_id: UUID,
    ) -> ManagedBacktest:
        async with self._lock:
            managed = self._runs.get(backtest_id)

        if managed is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        return managed

    @staticmethod
    def _snapshot(
        managed: ManagedBacktest,
    ) -> dict:
        run = managed.engine.run
        result = managed.result

        task_state = "not_started"

        if managed.task is not None:
            if managed.task.cancelled():
                task_state = "cancelled"
            elif managed.task.done():
                task_state = "completed"
            else:
                task_state = "running"

        snapshot = {
            "backtest_id": str(managed.backtest_id),
            "status": run.status.value,
            "task_state": task_state,
            "running": managed.running,
            "config": {
                "account_id": str(managed.config.account_id),
                "initial_balance": str(managed.config.initial_balance),
                "symbols": list(managed.config.symbols),
                "timeframes": list(managed.config.timeframes),
                "start": (
                    managed.config.start.isoformat()
                    if managed.config.start is not None
                    else None
                ),
                "end": (
                    managed.config.end.isoformat()
                    if managed.config.end is not None
                    else None
                ),
                "strategy_id": managed.config.strategy_id,
                "strategy_name": managed.config.strategy_name,
                "close_positions_at_end": (managed.config.close_positions_at_end),
            },
            "run": {
                "started_at": (
                    run.started_at.isoformat() if run.started_at is not None else None
                ),
                "completed_at": (
                    run.completed_at.isoformat()
                    if run.completed_at is not None
                    else None
                ),
                "current_time": (
                    run.current_time.isoformat()
                    if run.current_time is not None
                    else None
                ),
                "processed_events": run.processed_events,
                "processed_candles": run.processed_candles,
                "executions": len(run.executions),
                "pending_orders": len(run.pending_orders),
                "errors": list(run.errors),
            },
            "portfolio": {
                "balance": str(managed.engine.balance),
                "equity": str(managed.engine.equity),
                "realized_pnl": str(managed.engine.realized_pnl),
                "unrealized_pnl": str(managed.engine.unrealized_pnl),
            },
            "orchestration": None,
            "error": managed.error,
        }

        if result is not None:
            snapshot["orchestration"] = {
                "signals_received": result.signals_received,
                "risk_evaluations": result.risk_evaluations,
                "approved_decisions": result.approved_decisions,
                "rejected_decisions": result.rejected_decisions,
                "execution_orders": result.execution_orders,
                "executions": result.executions,
                "errors": list(result.errors),
            }

        return snapshot
