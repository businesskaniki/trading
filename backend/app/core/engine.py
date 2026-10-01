"""Top-level lifecycle orchestration for the Athena Quant Engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.database.session import SessionLocal
from app.market_data.consumer import MarketDataConsumer
from app.market_data.historical_synchronizer import (
    HistoricalDataSynchronizer,
)
from app.market_data.live import LiveTickHub
from app.market_data.service import MarketDataService
from app.market_data.subscription_manager import (
    MarketDataSubscriptionManager,
)
from engine.enums import EngineMode, EngineStatus
from engine.exceptions import (
    EnginePauseError,
    EngineResumeError,
    EngineShutdownError,
    EngineStartupError,
    EngineStateError,
)
from execution.bootstrap import (
    ExecutionRuntime,
    ExecutionRuntimeFactory,
)
from execution.strategy_deployer import LiveStrategyDeployer
from strategies.bootstrap import strategy_bootstrap
from strategies.core import StrategyMode, StrategyStatus
from strategies.synchronization import StrategySynchronizationService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineContext:
    """
    Mutable lifecycle state owned by AQEEngine.

    Runtime services themselves remain owned by ExecutionRuntime.
    """

    status: EngineStatus = EngineStatus.STOPPED
    mode: EngineMode = EngineMode.PAPER
    account_id: UUID | None = None


class AQEEngine:
    """
    Top-level lifecycle coordinator for the Athena Quant Engine.

    AQEEngine owns the lifecycle of one active account runtime.

    Dependency order:

        START

            Strategy discovery
                ↓
            Runtime composition
                ↓
            Strategy catalog synchronization
                ↓
            StrategyRun synchronization
                ↓
            Broker connection
                ↓
            Market-data infrastructure
                ↓
            Strategy runtime infrastructure
                ↓
            Risk → Execution pipeline
                ↓
            Persisted strategy deployment
                ↓
            RUNNING

        STOP

            Risk → Execution pipeline
                ↓
            Strategies
                ↓
            Market data
                ↓
            Broker
                ↓
            STOPPED

    AQEEngine does NOT implement:

        - broker execution
        - risk evaluation
        - strategy logic
        - market-data processing
        - order persistence
        - MT5 protocol handling

    It coordinates lifecycle and component ownership only.

    Constructing AQEEngine never starts trading infrastructure.
    """

    def __init__(
        self,
        *,
        runtime_factory: ExecutionRuntimeFactory | None = None,
        mode: EngineMode | None = None,
    ) -> None:
        """Initialize the AQE engine lifecycle coordinator."""

        self.context = EngineContext(
            mode=mode or self._resolve_mode(),
        )

        self.runtime_factory = (
            runtime_factory or ExecutionRuntimeFactory()
        )

        self._runtime: ExecutionRuntime | None = None
        self._broker_connected = False

        self._paused_strategy_ids: set[str] = set()

        self._strategy_deployer = LiveStrategyDeployer()

        logger.info(
            "AQE engine initialized. mode=%s status=%s",
            self.context.mode.value,
            self.context.status.value,
        )

    # ==================================================================
    # PUBLIC LIFECYCLE
    # ==================================================================

    async def start(
        self,
        account_id: UUID,
    ) -> None:
        """
        Start the complete AQE trading runtime for one account.

        Startup order:

            1. Discover installed strategies
            2. Compose account runtime
            3. Synchronize strategy definitions
            4. Synchronize account StrategyRuns
            5. Connect broker
            6. Start market-data infrastructure
            7. Start strategy runtime infrastructure
            8. Start Risk → Execution pipeline
            9. Deploy persisted LIVE/PAPER strategies
            10. Mark engine RUNNING

        Strategy discovery and persistence synchronization intentionally
        happen inside AQEEngine.start() rather than FastAPI application
        startup.

        This means starting the AQE engine is the explicit boundary at
        which an account's strategy catalog and StrategyRuns are
        reconciled.

        The Risk → Execution pipeline is started before persisted
        strategies are deployed. This prevents a strategy signal from
        being published before the pipeline has subscribed to
        StrategySignalEvent.

        FastAPI application startup must not call this method unless
        automatic trading startup is intentionally desired.
        """

        if self.context.status is not EngineStatus.STOPPED:
            raise EngineStateError(
                "AQE engine can only be started from STOPPED state. "
                f"Current state={self.context.status.value}."
            )

        if not isinstance(account_id, UUID):
            raise EngineStateError(
                "AQE engine start requires a valid account_id UUID."
            )

        self.context.status = EngineStatus.STARTING
        self.context.account_id = account_id
        self._paused_strategy_ids.clear()

        logger.info(
            "Starting AQE engine. account_id=%s mode=%s",
            account_id,
            self.context.mode.value,
        )

        try:
            # ----------------------------------------------------------
            # 1. Strategy discovery
            # ----------------------------------------------------------
            #
            # StrategyBootstrap owns StrategyDiscovery and populates
            # the global StrategyRegistry.
            #
            # Discovery does not start strategies, consume market data,
            # connect brokers, or execute orders.
            # ----------------------------------------------------------

            await self._discover_strategies()

            # ----------------------------------------------------------
            # 2. Compose account runtime
            # ----------------------------------------------------------
            #
            # StrategyRun synchronization requires the runtime account
            # owner (user_id), so runtime composition must happen before
            # account-specific strategy synchronization.
            # ----------------------------------------------------------

            self._runtime = await self.runtime_factory.create(
                account_id,
            )

            # ----------------------------------------------------------
            # 3. Strategy catalog + account StrategyRuns
            # ----------------------------------------------------------
            #
            # Both operations are performed against the same database
            # transaction.
            #
            # Strategy definitions are the persistent representation of
            # discovered Python strategy implementations.
            #
            # StrategyRuns are the account-specific persisted strategy
            # configurations.
            # ----------------------------------------------------------

            await self._synchronize_strategy_catalog()

            await self._synchronize_account_strategy_runs()

            # ----------------------------------------------------------
            # 4. Broker
            # ----------------------------------------------------------

            await self._start_broker()

            # ----------------------------------------------------------
            # 5. Market data
            # ----------------------------------------------------------

            await self._start_market_data()

            # ----------------------------------------------------------
            # 6. Strategy runtime infrastructure
            # ----------------------------------------------------------

            await self._start_strategy_runtime()

            # ----------------------------------------------------------
            # 7. Risk → Execution pipeline
            #
            # Start this BEFORE persisted strategies are deployed.
            # Strategy signals must never be emitted while the pipeline
            # is unsubscribed.
            # ----------------------------------------------------------

            await self._start_signal_pipeline()

            # ----------------------------------------------------------
            # 8. Deploy persisted strategies
            #
            # StrategyManager.create() starts the individual strategy
            # instances after the manager is running.
            #
            # At this point the Risk → Execution pipeline is already
            # listening.
            # ----------------------------------------------------------

            await self._deploy_strategies()

            # ----------------------------------------------------------
            # 9. Runtime is operational
            # ----------------------------------------------------------

            self.context.status = EngineStatus.RUNNING

            logger.info(
                "AQE engine started successfully. "
                "account_id=%s mode=%s",
                account_id,
                self.context.mode.value,
            )

        except EngineStartupError:
            await self._cleanup_failed_start()

            self.context.status = EngineStatus.STOPPED
            self.context.account_id = None
            self._paused_strategy_ids.clear()

            raise

        except Exception as exc:
            logger.exception(
                "AQE engine failed to start. account_id=%s",
                account_id,
            )

            await self._cleanup_failed_start()

            self.context.status = EngineStatus.STOPPED
            self.context.account_id = None
            self._paused_strategy_ids.clear()

            raise EngineStartupError(
                f"Failed to start AQE engine for account "
                f"{account_id}: {exc}"
            ) from exc

    async def stop(self) -> None:
        """
        Stop the complete AQE runtime.

        Shutdown occurs in reverse dependency order:

            Risk → Execution
                ↓
            Strategies
                ↓
            Historical synchronization
                ↓
            Live tick hub
                ↓
            Market-data consumer
                ↓
            Broker
        """

        if self.context.status is EngineStatus.STOPPED:
            return

        if self.context.status is EngineStatus.STOPPING:
            return

        self.context.status = EngineStatus.STOPPING

        logger.info(
            "Stopping AQE engine. account_id=%s",
            self.context.account_id,
        )

        shutdown_errors: list[BaseException] = []

        try:
            await self._stop_signal_pipeline()

        except Exception as exc:
            shutdown_errors.append(exc)

        try:
            await self._stop_strategy_runtime()

        except Exception as exc:
            shutdown_errors.append(exc)

        try:
            await self._stop_market_data()

        except Exception as exc:
            shutdown_errors.append(exc)

        try:
            await self._stop_broker()

        except Exception as exc:
            shutdown_errors.append(exc)

        self._runtime = None
        self._broker_connected = False
        self._paused_strategy_ids.clear()

        self.context.status = EngineStatus.STOPPED
        self.context.account_id = None

        if shutdown_errors:
            logger.error(
                "AQE engine stopped with %d shutdown error(s).",
                len(shutdown_errors),
            )

            raise EngineShutdownError(
                "AQE engine stopped, but one or more components "
                "failed during shutdown."
            ) from shutdown_errors[0]

        logger.info("AQE engine stopped.")

    async def pause(self) -> None:
        """
        Pause all currently running LIVE/PAPER strategies.

        Broker connectivity and market-data infrastructure remain
        active.

        Only strategies that were RUNNING when pause() was called are
        remembered and subsequently resumed by resume().
        """

        if self.context.status is not EngineStatus.RUNNING:
            raise EngineStateError(
                "AQE engine can only be paused from RUNNING state. "
                f"Current state={self.context.status.value}."
            )

        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            raise EngineStateError(
                "Cannot pause AQE engine because the strategy manager "
                "is not configured."
            )

        self._paused_strategy_ids.clear()

        instances = strategy_manager.instances()

        try:
            for instance in instances:
                if instance.mode not in {
                    StrategyMode.LIVE,
                    StrategyMode.PAPER,
                }:
                    continue

                if instance.status is not StrategyStatus.RUNNING:
                    continue

                await strategy_manager.pause_instance(
                    instance.strategy_id,
                )

                self._paused_strategy_ids.add(
                    str(instance.strategy_id),
                )

        except Exception as exc:
            logger.exception(
                "Failed to pause AQE strategy runtime. "
                "Restoring strategies already paused by engine."
            )

            try:
                await self._resume_paused_strategies()

            except Exception:
                logger.exception(
                    "Failed to restore strategies after pause failure."
                )

            self._paused_strategy_ids.clear()

            raise EnginePauseError(
                f"Failed to pause AQE engine: {exc}"
            ) from exc

        self.context.status = EngineStatus.PAUSED

        logger.info(
            "AQE engine paused. paused_strategy_ids=%s",
            sorted(self._paused_strategy_ids),
        )

    async def resume(self) -> None:
        """
        Resume only the strategies that AQEEngine paused.

        Strategies that were already paused before pause() remain
        paused.
        """

        if self.context.status is not EngineStatus.PAUSED:
            raise EngineStateError(
                "AQE engine can only be resumed from PAUSED state. "
                f"Current state={self.context.status.value}."
            )

        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            raise EngineStateError(
                "Cannot resume AQE engine because the strategy manager "
                "is not configured."
            )

        try:
            await self._resume_paused_strategies()

        except Exception as exc:
            logger.exception(
                "Failed to resume one or more AQE strategies."
            )

            raise EngineResumeError(
                f"Failed to resume AQE engine: {exc}"
            ) from exc

        self._paused_strategy_ids.clear()
        self.context.status = EngineStatus.RUNNING

        logger.info("AQE engine resumed.")

    # ==================================================================
    # STRATEGY DISCOVERY / SYNCHRONIZATION
    # ==================================================================

    async def _discover_strategies(self) -> None:
        """
        Discover installed strategy implementations.

        StrategyBootstrap owns StrategyDiscovery and the global
        StrategyRegistry.

        Discovery is intentionally separate from persistence
        synchronization:

            StrategyBootstrap
                ↓
            StrategyRegistry
                ↓
            StrategySynchronizationService
                ↓
            strategy_definitions
                ↓
            strategy_runs
        """

        logger.info(
            "Discovering AQE strategy implementations."
        )

        try:
            result = await strategy_bootstrap.start()

        except Exception as exc:
            logger.exception(
                "Failed to discover AQE strategy implementations."
            )

            raise EngineStartupError(
                "Failed to discover AQE strategies: "
                f"{exc}"
            ) from exc

        imported_count = len(
            getattr(
                result,
                "imported_modules",
                (),
            )
        )

        registered_count = len(
            getattr(
                result,
                "registered_strategies",
                (),
            )
        )

        logger.info(
            "AQE strategy discovery completed. "
            "imported_modules=%d registered_strategies=%d",
            imported_count,
            registered_count,
        )

    async def _synchronize_strategy_catalog(self) -> None:
        """
        Synchronize discovered strategies into the persistent catalog.

        This operation is intentionally part of AQEEngine.start().

        The Python StrategyRegistry is the source of truth for installed
        strategy implementations.

        StrategySynchronizationService reconciles that registry with
        the persistent strategy_definitions table.

        This method does not:

            - connect the broker
            - connect MT5
            - start market-data polling
            - subscribe to market data
            - create strategy instances
            - start the Risk → Execution pipeline
            - deploy StrategyRun records

        Account-specific StrategyRuns are synchronized separately by
        _synchronize_account_strategy_runs().
        """

        logger.info(
            "Synchronizing AQE strategy definition catalog."
        )

        try:
            async with SessionLocal() as db:
                async with db.begin():
                    service = StrategySynchronizationService(
                        db=db,
                    )

                    definitions = (
                        await service.synchronize_definitions(
                            commit=False,
                        )
                    )

            available_definitions = [
                definition
                for definition in definitions
                if definition.available
            ]

            logger.info(
                "AQE strategy definition catalog synchronized: "
                "definitions=%d available=%d unavailable=%d",
                len(definitions),
                len(available_definitions),
                len(definitions) - len(available_definitions),
            )

            logger.debug(
                "Available AQE strategy definitions: %s",
                tuple(
                    definition.name
                    for definition in available_definitions
                ),
            )

        except Exception as exc:
            logger.exception(
                "Failed to synchronize AQE strategy definition catalog."
            )

            raise EngineStartupError(
                "Failed to synchronize the AQE strategy definition "
                f"catalog: {exc}"
            ) from exc

    async def _synchronize_account_strategy_runs(self) -> None:
        """
        Provision missing StrategyRun records for the active account.

        StrategyRun synchronization happens when an AQE account runtime
        starts, not during FastAPI application startup.

        The operation is idempotent:

            - existing StrategyRuns are preserved
            - missing StrategyRuns are created
            - strategy configuration is derived from the registered
              StrategyDefinition
            - disabled runs remain disabled
            - no strategy instance is started here

        Actual strategy instances are deployed later by
        LiveStrategyDeployer after the Risk → Execution pipeline is
        running.
        """

        runtime = self._require_runtime()

        account_id = runtime.account.account_id
        user_id = runtime.account.user_id

        logger.info(
            "Synchronizing account strategy runs. "
            "account_id=%s user_id=%s",
            account_id,
            user_id,
        )

        try:
            async with SessionLocal() as db:
                async with db.begin():
                    service = StrategySynchronizationService(
                        db=db,
                    )

                    strategy_runs = (
                        await service.synchronize_account(
                            account_id=account_id,
                            user_id=user_id,
                            commit=False,
                        )
                    )

            enabled_count = sum(
                1
                for run in strategy_runs
                if run.enabled
            )

            logger.info(
                "Account strategy runs synchronized. "
                "account_id=%s user_id=%s runs=%d enabled=%d",
                account_id,
                user_id,
                len(strategy_runs),
                enabled_count,
            )

            logger.debug(
                "Account strategy runs: %s",
                tuple(
                    (
                        str(run.id),
                        run.strategy_name,
                        run.status.value
                        if hasattr(run.status, "value")
                        else str(run.status),
                        run.enabled,
                    )
                    for run in strategy_runs
                ),
            )

        except Exception as exc:
            logger.exception(
                "Failed to synchronize account strategy runs. "
                "account_id=%s user_id=%s",
                account_id,
                user_id,
            )

            raise EngineStartupError(
                "Failed to synchronize strategy runs for account "
                f"{account_id}: {exc}"
            ) from exc

    # ==================================================================
    # STARTUP
    # ==================================================================

    async def _start_broker(self) -> None:
        """
        Connect the account-specific broker.

        RuntimeAccount.broker_credentials is the only credential source.

        Credentials originate from the AQE TradingAccount and are
        decrypted by RuntimeAccountResolver.

        They are never obtained from the MT5 bridge environment.
        """

        runtime = self._require_runtime()

        if not self._requires_broker:
            logger.info(
                "Broker startup skipped for engine mode=%s.",
                self.context.mode.value,
            )
            return

        logger.info(
            "Connecting broker. broker=%s account_id=%s",
            runtime.account.broker,
            runtime.account.account_id,
        )

        try:
            await runtime.broker_manager.connect(
                runtime.account.broker_credentials,
            )

        except Exception as exc:
            raise EngineStartupError(
                f"Failed to connect broker for account "
                f"{runtime.account.account_id}: {exc}"
            ) from exc

        self._broker_connected = True

        logger.info(
            "Broker connected. broker=%s account_id=%s",
            runtime.account.broker,
            runtime.account.account_id,
        )

    async def _start_market_data(self) -> None:
        """Start all market-data runtime components."""

        runtime = self._require_runtime()

        try:
            consumer = runtime.market_data_consumer

            if consumer is not None:
                await consumer.start()

            hub = runtime.live_tick_hub

            if hub is not None:
                await hub.start()

            subscription_manager = (
                runtime.market_data_subscription_manager
            )

            if subscription_manager is not None:
                await subscription_manager.reconcile()

            historical_synchronizer = (
                runtime.historical_data_synchronizer
            )

            if historical_synchronizer is not None:
                await historical_synchronizer.start()

        except Exception as exc:
            raise EngineStartupError(
                f"Failed to start AQE market-data runtime: {exc}"
            ) from exc

        logger.info("AQE market-data runtime started.")

    async def _start_strategy_runtime(self) -> None:
        """
        Start strategy runtime infrastructure.

        Strategy implementations have already been discovered and
        synchronized by the engine startup sequence.

        StrategyManager.start() is therefore responsible only for
        starting the runtime dispatcher/infrastructure.

        Individual LIVE/PAPER strategy instances are deployed later by
        LiveStrategyDeployer.
        """

        runtime = self._require_runtime()
        strategy_manager = runtime.strategy_manager

        if strategy_manager is None:
            logger.warning(
                "No strategy manager configured. "
                "AQE will run without strategies."
            )
            return

        try:
            await strategy_manager.start()

        except Exception as exc:
            raise EngineStartupError(
                f"Failed to start AQE strategy runtime: {exc}"
            ) from exc

        logger.info("AQE strategy runtime started.")

    async def _start_signal_pipeline(self) -> None:
        """
        Start the Strategy → Risk → Execution event pipeline.

        This must happen before persisted strategies are deployed so
        that StrategySignalEvent cannot be emitted before the pipeline
        is subscribed.
        """

        runtime = self._require_runtime()
        pipeline = runtime.live_pipeline

        if pipeline is None:
            logger.warning(
                "No live signal pipeline configured. "
                "Risk → Execution will not process strategy signals."
            )
            return

        try:
            await pipeline.start()

        except Exception as exc:
            raise EngineStartupError(
                "Failed to start AQE Risk → Execution pipeline: "
                f"{exc}"
            ) from exc

        logger.info(
            "AQE Risk → Execution pipeline started."
        )

    async def _deploy_strategies(self) -> None:
        """
        Deploy persisted LIVE/PAPER strategies for the active account.

        StrategyRun persistence is intentionally accessed through
        LiveStrategyDeployer rather than directly from AQEEngine.

        Only StrategyRun records belonging to the runtime account owner
        are considered by the deployer.

        The deployment is performed after the execution pipeline is
        listening, so deployed strategies can safely emit signals.
        """

        runtime = self._require_runtime()
        strategy_manager = runtime.strategy_manager

        if strategy_manager is None:
            logger.info(
                "Strategy deployment skipped because no strategy "
                "manager is configured."
            )
            return

        account_id = runtime.account.account_id
        user_id = runtime.account.user_id

        try:
            result = await self._strategy_deployer.deploy_for_account(
                account_id=account_id,
                user_id=user_id,
                strategy_manager=strategy_manager,
            )

        except Exception as exc:
            raise EngineStartupError(
                f"Failed to deploy persisted strategies for account "
                f"{account_id}: {exc}"
            ) from exc

        if result.failed_count:
            logger.warning(
                "AQE strategy deployment completed with failures. "
                "account_id=%s user_id=%s deployed=%s skipped=%s "
                "failed=%s failed_strategy_ids=%s",
                account_id,
                user_id,
                result.deployed_count,
                result.skipped_count,
                result.failed_count,
                list(result.failed_strategy_ids),
            )

        else:
            logger.info(
                "AQE strategy deployment completed. "
                "account_id=%s user_id=%s deployed=%s skipped=%s "
                "failed=%s",
                account_id,
                user_id,
                result.deployed_count,
                result.skipped_count,
                result.failed_count,
            )

    # ==================================================================
    # SHUTDOWN
    # ==================================================================

    async def _stop_signal_pipeline(self) -> None:
        """Stop the Strategy → Risk → Execution pipeline."""

        runtime = self._runtime

        if runtime is None:
            return

        pipeline = runtime.live_pipeline

        if pipeline is None:
            return

        try:
            await pipeline.stop()

        except Exception as exc:
            logger.exception(
                "Failed to stop AQE Risk → Execution pipeline."
            )

            raise EngineShutdownError(
                "Failed to stop AQE Risk → Execution pipeline: "
                f"{exc}"
            ) from exc

    async def _stop_strategy_runtime(self) -> None:
        """
        Stop all strategy instances and strategy runtime infrastructure.
        """

        runtime = self._runtime

        if runtime is None:
            return

        strategy_manager = runtime.strategy_manager

        if strategy_manager is None:
            return

        try:
            await strategy_manager.stop()

        except Exception as exc:
            logger.exception(
                "Failed to stop AQE strategy runtime."
            )

            raise EngineShutdownError(
                f"Failed to stop AQE strategy runtime: {exc}"
            ) from exc

    async def _stop_market_data(self) -> None:
        """Stop market-data components in reverse dependency order."""

        runtime = self._runtime

        if runtime is None:
            return

        shutdown_errors: list[BaseException] = []

        historical_synchronizer = (
            runtime.historical_data_synchronizer
        )

        if historical_synchronizer is not None:
            try:
                await historical_synchronizer.stop()

            except Exception as exc:
                logger.exception(
                    "Failed to stop historical-data synchronizer."
                )

                shutdown_errors.append(exc)

        hub = runtime.live_tick_hub

        if hub is not None:
            try:
                await hub.stop()

            except Exception as exc:
                logger.exception(
                    "Failed to stop live tick hub."
                )

                shutdown_errors.append(exc)

        consumer = runtime.market_data_consumer

        if consumer is not None:
            try:
                await consumer.stop()

            except Exception as exc:
                logger.exception(
                    "Failed to stop market-data consumer."
                )

                shutdown_errors.append(exc)

        if shutdown_errors:
            raise EngineShutdownError(
                "One or more market-data components failed during "
                "shutdown."
            ) from shutdown_errors[0]

    async def _stop_broker(self) -> None:
        """Disconnect the account-specific broker."""

        runtime = self._runtime

        if runtime is None:
            return

        if not self._broker_connected:
            return

        try:
            await runtime.broker_manager.disconnect()

        except Exception as exc:
            logger.exception(
                "Failed to disconnect broker."
            )

            raise EngineShutdownError(
                f"Failed to disconnect broker: {exc}"
            ) from exc

        finally:
            self._broker_connected = False

    async def _cleanup_failed_start(self) -> None:
        """
        Best-effort cleanup after a failed startup.

        Components are stopped in reverse dependency order.

        Cleanup errors are logged but do not replace the original
        startup exception.
        """

        try:
            await self._stop_signal_pipeline()

        except Exception:
            logger.exception(
                "Startup cleanup failed while stopping "
                "signal pipeline."
            )

        try:
            await self._stop_strategy_runtime()

        except Exception:
            logger.exception(
                "Startup cleanup failed while stopping strategies."
            )

        try:
            await self._stop_market_data()

        except Exception:
            logger.exception(
                "Startup cleanup failed while stopping market data."
            )

        try:
            await self._stop_broker()

        except Exception:
            logger.exception(
                "Startup cleanup failed while stopping broker."
            )

        self._runtime = None
        self._broker_connected = False
        self._paused_strategy_ids.clear()

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(self) -> dict[str, Any]:
        """
        Return the current AQE runtime state.

        Broker credentials and passwords are intentionally excluded.
        """

        runtime = self._runtime

        account_snapshot: dict[str, Any] | None = None

        if runtime is not None:
            account = runtime.account

            account_snapshot = {
                "id": str(account.account_id),
                "broker": account.broker,
                "login": account.login,
                "server": account.server,
            }

        strategy_manager = self.strategy_manager

        strategy_snapshot: dict[str, Any] = {
            "configured": strategy_manager is not None,
            "running": self._strategy_manager_running(),
            "paused_strategy_ids": (
                self._paused_strategy_ids_snapshot()
            ),
        }

        if strategy_manager is not None:
            strategy_snapshot.update(
                {
                    "instance_count": (
                        strategy_manager.instance_count
                    ),
                    "active_instance_count": (
                        strategy_manager.active_instance_count
                    ),
                    "instances": strategy_manager.snapshots(),
                    "routing": strategy_manager.routing_snapshot(),
                }
            )

        return {
            "status": self.context.status.value,
            "mode": self.context.mode.value,
            "account": account_snapshot,
            "broker": {
                "required": self._requires_broker,
                "connected": self._broker_connected,
            },
            "market_data": {
                "consumer_running": (
                    self._market_data_consumer_running()
                ),
                "live_tick_hub_running": (
                    self._live_tick_hub_running()
                ),
                "historical_sync_running": (
                    self._historical_sync_running()
                ),
            },
            "strategies": strategy_snapshot,
            "pipeline": {
                "configured": self.live_pipeline is not None,
                "running": self._live_pipeline_running(),
            },
            "execution": {
                "configured": self.execution_engine is not None,
            },
        }

    # ==================================================================
    # RUNTIME ACCESSORS
    # ==================================================================

    @property
    def runtime(self) -> ExecutionRuntime | None:
        """Return the current execution runtime."""

        return self._runtime

    @property
    def broker_manager(self):
        """Return the runtime broker manager."""

        runtime = self._runtime

        return (
            runtime.broker_manager
            if runtime is not None
            else None
        )

    @property
    def market_data_consumer(
        self,
    ) -> MarketDataConsumer | None:
        """Return the runtime market-data consumer."""

        runtime = self._runtime

        return (
            runtime.market_data_consumer
            if runtime is not None
            else None
        )

    @property
    def live_tick_hub(
        self,
    ) -> LiveTickHub | None:
        """Return the runtime live tick hub."""

        runtime = self._runtime

        return (
            runtime.live_tick_hub
            if runtime is not None
            else None
        )

    @property
    def market_data_subscription_manager(
        self,
    ) -> MarketDataSubscriptionManager | None:
        """Return the runtime market-data subscription manager."""

        runtime = self._runtime

        return (
            runtime.market_data_subscription_manager
            if runtime is not None
            else None
        )

    @property
    def historical_synchronizer(
        self,
    ) -> HistoricalDataSynchronizer | None:
        """Return the runtime historical synchronizer."""

        runtime = self._runtime

        return (
            runtime.historical_data_synchronizer
            if runtime is not None
            else None
        )

    @property
    def market_data_service(
        self,
    ) -> MarketDataService | None:
        """Return the runtime market-data service."""

        runtime = self._runtime

        return (
            runtime.market_data_service
            if runtime is not None
            else None
        )

    @property
    def strategy_manager(self):
        """Return the runtime strategy manager."""

        runtime = self._runtime

        return (
            runtime.strategy_manager
            if runtime is not None
            else None
        )

    @property
    def live_pipeline(self):
        """Return the live signal pipeline."""

        runtime = self._runtime

        return (
            runtime.live_pipeline
            if runtime is not None
            else None
        )

    @property
    def execution_engine(self):
        """Return the execution engine."""

        runtime = self._runtime

        return (
            runtime.execution_engine
            if runtime is not None
            else None
        )

    # ==================================================================
    # COMPONENT STATE
    # ==================================================================

    def _market_data_consumer_running(self) -> bool:
        """Return whether the market-data consumer reports running."""

        consumer = self.market_data_consumer

        if consumer is None:
            return False

        try:
            status = consumer.status()

        except Exception:
            logger.exception(
                "Failed to read market-data consumer status."
            )

            return False

        return bool(
            status.get(
                "running",
                False,
            )
        )

    def _live_tick_hub_running(self) -> bool:
        """Return whether the live tick hub is started."""

        hub = self.live_tick_hub

        if hub is None:
            return False

        return bool(
            getattr(
                hub,
                "_started",
                False,
            )
        )

    def _historical_sync_running(self) -> bool:
        """Return whether historical synchronization is running."""

        synchronizer = self.historical_synchronizer

        if synchronizer is None:
            return False

        return bool(
            getattr(
                synchronizer,
                "_running",
                False,
            )
        )

    def _strategy_manager_running(self) -> bool:
        """Return whether the strategy manager is running."""

        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            return False

        running = getattr(
            strategy_manager,
            "running",
            None,
        )

        if running is not None:
            return bool(running)

        is_running = getattr(
            strategy_manager,
            "is_running",
            None,
        )

        if is_running is not None:
            return bool(is_running)

        return False

    def _live_pipeline_running(self) -> bool:
        """Return whether the live signal pipeline is started."""

        pipeline = self.live_pipeline

        if pipeline is None:
            return False

        started = getattr(
            pipeline,
            "started",
            None,
        )

        if started is not None:
            return bool(started)

        running = getattr(
            pipeline,
            "running",
            None,
        )

        if running is not None:
            return bool(running)

        is_running = getattr(
            pipeline,
            "is_running",
            None,
        )

        if is_running is not None:
            return bool(is_running)

        return False

    def _paused_strategy_ids_snapshot(self) -> list[str]:
        """Return paused strategy IDs in deterministic order."""

        return sorted(
            self._paused_strategy_ids,
        )

    async def _resume_paused_strategies(self) -> None:
        """
        Resume strategies previously paused by AQEEngine.

        Strategies removed while the engine was paused are skipped.
        """

        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            raise EngineStateError(
                "Cannot resume AQE strategies because the strategy "
                "manager is not configured."
            )

        strategy_ids = tuple(
            self._paused_strategy_ids,
        )

        for strategy_id in strategy_ids:
            instance = strategy_manager.get(
                strategy_id,
            )

            if instance is None:
                logger.warning(
                    "Strategy instance no longer exists while "
                    "resuming: id=%s",
                    strategy_id,
                )
                continue

            if instance.status is not StrategyStatus.PAUSED:
                logger.info(
                    "Skipping strategy resume because strategy "
                    "is no longer paused: id=%s status=%s",
                    strategy_id,
                    instance.status.value,
                )
                continue

            await strategy_manager.resume_instance(
                strategy_id,
            )

    # ==================================================================
    # VALIDATION / CONFIGURATION
    # ==================================================================

    @property
    def _requires_broker(self) -> bool:
        """Return whether the selected engine mode requires a broker."""

        return self.context.mode in {
            EngineMode.LIVE,
            EngineMode.PAPER,
        }

    @staticmethod
    def _resolve_mode() -> EngineMode:
        """
        Resolve configured AQE engine mode.

        Invalid configuration falls back to PAPER rather than preventing
        the backend application itself from starting.
        """

        raw_mode = getattr(
            settings,
            "AQE_ENGINE_MODE",
            None,
        )

        if raw_mode is None:
            raw_mode = getattr(
                settings,
                "ENGINE_MODE",
                None,
            )

        if raw_mode is None:
            return EngineMode.PAPER

        if isinstance(
            raw_mode,
            EngineMode,
        ):
            return raw_mode

        try:
            return EngineMode(
                str(raw_mode).strip().upper(),
            )

        except ValueError:
            logger.warning(
                "Invalid AQE engine mode %r. "
                "Falling back to PAPER.",
                raw_mode,
            )

            return EngineMode.PAPER

    def _require_runtime(self) -> ExecutionRuntime:
        """Return the active execution runtime or raise."""

        runtime = self._runtime

        if runtime is None:
            raise EngineStateError(
                "AQE runtime has not been created."
            )

        return runtime


# ======================================================================
# GLOBAL ENGINE
# ======================================================================

_aqe_engine = AQEEngine()


def get_aqe_engine() -> AQEEngine:
    """
    Return the application-wide AQE engine instance.

    Calling this function only retrieves the lifecycle coordinator.

    It does NOT start broker, market-data, strategy, risk, or
    execution infrastructure.
    """

    return _aqe_engine