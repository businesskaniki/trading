"""Application-level lifecycle management for AQE backtests."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from .engine import BacktestConfig, BacktestEngine, BacktestStatus
from .orchestration import (
    BacktestOrchestrationResult,
    BacktestOrchestrator,
)


BacktestOrchestratorFactory = Callable[
    [BacktestConfig],
    BacktestOrchestrator | Awaitable[BacktestOrchestrator],
]


@dataclass(slots=True)
class ManagedBacktest:
    """
    Application-level state for one backtest run.

    The actual simulation state remains owned by BacktestEngine.

    This object owns only:
        - lifecycle/task ownership
        - resolved configuration snapshot
        - result/error capture
        - registration in BacktestService
    """

    backtest_id: UUID
    config: BacktestConfig
    orchestrator: BacktestOrchestrator

    task: asyncio.Task[BacktestOrchestrationResult] | None = None
    result: BacktestOrchestrationResult | None = None
    error: str | None = None

    @property
    def engine(self) -> BacktestEngine:
        """Return the simulation engine owned by the orchestrator."""

        return self.orchestrator.engine

    @property
    def status(self) -> BacktestStatus:
        """Return the current backtest lifecycle status."""

        return self.engine.run.status

    @property
    def running(self) -> bool:
        """
        Return whether this backtest currently has an active task and
        remains in RUNNING simulation state.
        """

        return (
            self.task is not None
            and not self.task.done()
            and self.status == BacktestStatus.RUNNING
        )


class BacktestService:
    """
    Application service responsible for backtest lifecycle.

    BacktestEngine owns:
        - historical-event simulation
        - portfolio accounting
        - positions
        - fills
        - pending orders
        - execution simulation

    BacktestOrchestrator owns:
        - active strategy runtime
        - strategy -> signal
        - signal -> risk
        - risk -> execution
        - feeding approved orders back to BacktestEngine

    BacktestService owns:
        - run registration
        - background task management
        - lifecycle operations
        - API-facing snapshots

    This service intentionally does NOT decide:
        - which strategies are active
        - which symbols are selected
        - which timeframes are required
        - how strategy signals are generated
        - how risk is calculated
        - how historical data is loaded

    Those decisions belong to the lower backtest composition and
    orchestration layers.

    The service remains in-memory by design. Database persistence can
    be added above this layer without coupling persistence to the
    simulation engine.
    """

    def __init__(
        self,
        orchestrator_factory: BacktestOrchestratorFactory,
    ) -> None:
        self._orchestrator_factory = orchestrator_factory

        self._runs: dict[UUID, ManagedBacktest] = {}

        # Protects creation/removal and task assignment.
        self._lock = asyncio.Lock()

    # ==================================================================
    # CREATE
    # ==================================================================

    async def create(
        self,
        config: BacktestConfig,
    ) -> dict[str, Any]:
        """
        Create and register a backtest without starting it.

        The supplied configuration is the request-level configuration.

        The composition layer may resolve additional account-level
        configuration while constructing the BacktestEngine, including:

            - enabled account symbols
            - strategy timeframes
            - contract sizes
            - normalized strategy configuration

        The configuration stored by ManagedBacktest is therefore taken
        from the constructed BacktestEngine rather than blindly retaining
        the original request configuration.
        """

        orchestrator = await self._build_orchestrator(config)

        engine = orchestrator.engine
        backtest_id = engine.run.run_id

        # --------------------------------------------------------------
        # IMPORTANT
        # --------------------------------------------------------------
        #
        # The composition layer constructs BacktestEngine with the
        # fully resolved BacktestConfig:
        #
        #     BacktestEngine(
        #         market_data=market_data,
        #         config=resolved_config,
        #     )
        #
        # The API request config may intentionally contain:
        #
        #     symbols=()
        #     timeframes=()
        #     contract_sizes={}
        #
        # because those values are resolved from the account.
        #
        # The engine's config is therefore the authoritative
        # configuration for the created backtest.
        #
        resolved_config = getattr(
            engine,
            "config",
            None,
        )

        if not isinstance(
            resolved_config,
            BacktestConfig,
        ):
            raise TypeError(
                "BacktestEngine must expose its resolved "
                "BacktestConfig through the 'config' attribute."
            )

        managed = ManagedBacktest(
            backtest_id=backtest_id,
            config=resolved_config,
            orchestrator=orchestrator,
        )

        async with self._lock:
            if backtest_id in self._runs:
                raise RuntimeError(
                    f"Backtest {backtest_id} is already registered."
                )

            self._runs[backtest_id] = managed

        return self.snapshot(backtest_id)

    # ==================================================================
    # START
    # ==================================================================

    async def start(
        self,
        backtest_id: UUID,
    ) -> dict[str, Any]:
        """
        Start a registered backtest in the background.

        The caller does not wait for the simulation to finish.
        """

        async with self._lock:
            managed = self._runs.get(backtest_id)

            if managed is None:
                raise KeyError(
                    f"Backtest {backtest_id} was not found."
                )

            if managed.task is not None and not managed.task.done():
                raise RuntimeError(
                    f"Backtest {backtest_id} is already running."
                )

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

    # ==================================================================
    # STOP
    # ==================================================================

    async def stop(
        self,
        backtest_id: UUID,
    ) -> dict[str, Any]:
        """
        Request cooperative shutdown of a running backtest.

        BacktestEngine.stop() changes the simulation state to STOPPED.
        The simulation loop observes that state between events and exits
        cleanly.
        """

        managed = await self._get_managed(backtest_id)

        if managed.task is None or managed.task.done():
            if managed.status == BacktestStatus.CREATED:
                raise RuntimeError(
                    f"Backtest {backtest_id} has not been started."
                )

            return self.snapshot(backtest_id)

        if managed.status == BacktestStatus.RUNNING:
            managed.engine.stop()

        return self.snapshot(backtest_id)

    # ==================================================================
    # GET
    # ==================================================================

    async def get(
        self,
        backtest_id: UUID,
    ) -> dict[str, Any]:
        """
        Return the current API-facing state of a backtest.
        """

        await self._get_managed(backtest_id)

        return self.snapshot(backtest_id)

    # ==================================================================
    # LIST
    # ==================================================================

    async def list(self) -> list[dict[str, Any]]:
        """
        Return all registered backtests.

        Newest runs are returned first.
        """

        async with self._lock:
            runs = list(self._runs.values())

        runs.sort(
            key=lambda item: (
                item.engine.run.started_at
                or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )

        return [
            self._snapshot(managed)
            for managed in runs
        ]

    # ==================================================================
    # REMOVE
    # ==================================================================

    async def remove(
        self,
        backtest_id: UUID,
    ) -> None:
        """
        Remove a completed, stopped, or failed backtest.

        Running backtests cannot be removed.
        """

        async with self._lock:
            managed = self._runs.get(backtest_id)

            if managed is None:
                raise KeyError(
                    f"Backtest {backtest_id} was not found."
                )

            if managed.task is not None and not managed.task.done():
                raise RuntimeError(
                    f"Backtest {backtest_id} is still running."
                )

            self._runs.pop(
                backtest_id,
                None,
            )

    # ==================================================================
    # STOP ALL
    # ==================================================================

    async def stop_all(self) -> None:
        """
        Request cooperative shutdown of all currently running
        backtests.

        Intended for application shutdown.
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

        tasks = [
            managed.task
            for managed in running
            if managed.task is not None
        ]

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(
        self,
        backtest_id: UUID,
    ) -> dict[str, Any]:
        """
        Return a synchronous API-facing snapshot.

        This helper intentionally performs no additional lookup or
        awaitable work once the run is registered.
        """

        managed = self._runs.get(backtest_id)

        if managed is None:
            raise KeyError(
                f"Backtest {backtest_id} was not found."
            )

        return self._snapshot(managed)

    # ==================================================================
    # BACKGROUND TASK
    # ==================================================================

    async def _run(
        self,
        managed: ManagedBacktest,
    ) -> BacktestOrchestrationResult | None:
        """
        Execute the orchestrator and capture its terminal result.

        Exceptions are stored on ManagedBacktest so that background
        asyncio tasks never produce unobserved task exceptions.
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

                managed.engine.run.errors.append(
                    str(exc),
                )

            return None

    # ==================================================================
    # FACTORY
    # ==================================================================

    async def _build_orchestrator(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Resolve either a synchronous or asynchronous orchestrator
        factory.
        """

        result = self._orchestrator_factory(config)

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(
            result,
            BacktestOrchestrator,
        ):
            raise TypeError(
                "Backtest orchestrator factory must return "
                "BacktestOrchestrator."
            )

        return result

    # ==================================================================
    # LOOKUP
    # ==================================================================

    async def _get_managed(
        self,
        backtest_id: UUID,
    ) -> ManagedBacktest:
        """
        Resolve a registered backtest.
        """

        async with self._lock:
            managed = self._runs.get(backtest_id)

        if managed is None:
            raise KeyError(
                f"Backtest {backtest_id} was not found."
            )

        return managed

    # ==================================================================
    # SNAPSHOT IMPLEMENTATION
    # ==================================================================

    @classmethod
    def _snapshot(
        cls,
        managed: ManagedBacktest,
    ) -> dict[str, Any]:
        """
        Build the API-facing representation of one backtest.

        The configuration shown here is the resolved configuration
        actually used by BacktestEngine.

        This means account-derived fields such as:

            - symbols
            - timeframes
            - contract_sizes

        are visible immediately after backtest creation.
        """

        run = managed.engine.run
        result = managed.result
        config = managed.config

        task_state = "not_started"

        if managed.task is not None:
            if managed.task.cancelled():
                task_state = "cancelled"

            elif managed.task.done():
                task_state = "completed"

            else:
                task_state = "running"

        snapshot: dict[str, Any] = {
            "backtest_id": str(managed.backtest_id),
            "status": run.status.value,
            "task_state": task_state,
            "running": managed.running,
            "config": cls._serialize_config(config),
            "run": {
                "started_at": cls._serialize_value(
                    run.started_at,
                ),
                "completed_at": cls._serialize_value(
                    run.completed_at,
                ),
                "current_time": cls._serialize_value(
                    run.current_time,
                ),
                "processed_events": run.processed_events,
                "processed_candles": run.processed_candles,
                "executions": len(run.executions),
                "pending_orders": len(run.pending_orders),
                "errors": list(run.errors),
            },
            "portfolio": {
                "balance": cls._serialize_value(
                    managed.engine.balance,
                ),
                "equity": cls._serialize_value(
                    managed.engine.equity,
                ),
                "realized_pnl": cls._serialize_value(
                    managed.engine.realized_pnl,
                ),
                "unrealized_pnl": cls._serialize_value(
                    managed.engine.unrealized_pnl,
                ),
            },
            "orchestration": None,
            "error": managed.error,
        }

        if result is not None:
            snapshot["orchestration"] = cls._serialize_result(
                result,
            )

        return snapshot

    # ==================================================================
    # CONFIG SERIALIZATION
    # ==================================================================

    @classmethod
    def _serialize_config(
        cls,
        config: BacktestConfig,
    ) -> dict[str, Any]:
        """
        Serialize BacktestConfig without coupling this service to one
        particular generation of the configuration model.

        The canonical account-level fields are exposed explicitly.
        Additional resolved-universe fields are included when present.
        """

        serialized: dict[str, Any] = {}

        # --------------------------------------------------------------
        # Canonical account-level configuration
        # --------------------------------------------------------------

        if hasattr(config, "account_id"):
            serialized["account_id"] = cls._serialize_value(
                getattr(config, "account_id"),
            )

        if hasattr(config, "initial_balance"):
            serialized["initial_balance"] = cls._serialize_value(
                getattr(config, "initial_balance"),
            )

        if hasattr(config, "period"):
            serialized["period"] = cls._serialize_value(
                getattr(config, "period"),
            )

        if hasattr(config, "start"):
            serialized["start"] = cls._serialize_value(
                getattr(config, "start"),
            )

        if hasattr(config, "end"):
            serialized["end"] = cls._serialize_value(
                getattr(config, "end"),
            )

        if hasattr(config, "close_positions_at_end"):
            serialized["close_positions_at_end"] = cls._serialize_value(
                getattr(
                    config,
                    "close_positions_at_end",
                ),
            )

        # --------------------------------------------------------------
        # Resolved market universe
        # --------------------------------------------------------------

        if hasattr(config, "symbols"):
            serialized["symbols"] = cls._serialize_value(
                getattr(config, "symbols"),
            )

        if hasattr(config, "timeframes"):
            serialized["timeframes"] = cls._serialize_value(
                getattr(config, "timeframes"),
            )

        if hasattr(config, "contract_sizes"):
            serialized["contract_sizes"] = cls._serialize_value(
                getattr(config, "contract_sizes"),
            )

        # --------------------------------------------------------------
        # Resolved strategy universe
        # --------------------------------------------------------------

        if hasattr(config, "strategies"):
            serialized["strategies"] = cls._serialize_value(
                getattr(config, "strategies"),
            )

        elif hasattr(config, "strategy_configs"):
            serialized["strategies"] = cls._serialize_value(
                getattr(config, "strategy_configs"),
            )

        else:
            if hasattr(config, "strategy_ids"):
                serialized["strategy_ids"] = cls._serialize_value(
                    getattr(config, "strategy_ids"),
                )

            if hasattr(config, "strategy_names"):
                serialized["strategy_names"] = cls._serialize_value(
                    getattr(config, "strategy_names"),
                )

        return serialized

    # ==================================================================
    # RESULT SERIALIZATION
    # ==================================================================

    @classmethod
    def _serialize_result(
        cls,
        result: BacktestOrchestrationResult,
    ) -> dict[str, Any]:
        """
        Serialize orchestration statistics.

        The core counters remain stable. Optional multi-strategy and
        per-symbol result collections are included when the result
        object exposes them.
        """

        serialized: dict[str, Any] = {
            "signals_received": result.signals_received,
            "risk_evaluations": result.risk_evaluations,
            "approved_decisions": result.approved_decisions,
            "rejected_decisions": result.rejected_decisions,
            "execution_orders": result.execution_orders,
            "executions": cls._serialize_value(
                result.executions,
            ),
            "errors": list(result.errors),
        }

        if hasattr(result, "risk_decisions"):
            serialized["risk_decisions"] = cls._serialize_value(
                result.risk_decisions,
            )

        if hasattr(result, "strategy_results"):
            serialized["strategy_results"] = cls._serialize_value(
                getattr(
                    result,
                    "strategy_results",
                ),
            )

        if hasattr(result, "symbol_results"):
            serialized["symbol_results"] = cls._serialize_value(
                getattr(
                    result,
                    "symbol_results",
                ),
            )

        if hasattr(result, "portfolio_result"):
            serialized["portfolio_result"] = cls._serialize_value(
                getattr(
                    result,
                    "portfolio_result",
                ),
            )

        if hasattr(result, "metrics"):
            serialized["metrics"] = cls._serialize_value(
                getattr(
                    result,
                    "metrics",
                ),
            )

        return serialized

    # ==================================================================
    # GENERIC SERIALIZATION
    # ==================================================================

    @classmethod
    def _serialize_value(
        cls,
        value: Any,
    ) -> Any:
        """
        Convert common AQE domain values into JSON-safe structures.

        Supported:
            UUID
            Decimal
            datetime/date
            Enum
            dataclasses
            mappings
            tuples/lists/sets
            arbitrary objects exposing ``model_dump``

        Strings are preserved exactly.
        """

        if value is None:
            return None

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, Enum):
            return value.value

        if is_dataclass(value):
            return cls._serialize_value(
                asdict(value),
            )

        model_dump = getattr(
            value,
            "model_dump",
            None,
        )

        if callable(model_dump):
            return cls._serialize_value(
                model_dump(),
            )

        if isinstance(value, Mapping):
            return {
                str(key): cls._serialize_value(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                cls._serialize_value(item)
                for item in value
            ]

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        return str(value)