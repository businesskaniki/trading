from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.market_data.consumer import MarketDataConsumer
from app.market_data.live import LiveTickHub
from app.market_data.subscription_manager import MarketDataSubscriptionManager
from app.market_data.historical_synchronizer import (
    HistoricalDataSynchronizer,
)
from app.services.historical_data_service import HistoricalDataService
from app.market_data.service import MarketDataService
from app.services.mt5_bridge_service import MT5BridgeService
from engine.enums import EngineMode, EngineStatus
from engine.exceptions import EngineStateError
from execution.bootstrap import ExecutionRuntime, ExecutionRuntimeFactory
from strategies.core import StrategyMode, StrategyStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineContext:
    """
    Mutable runtime state owned by AQEEngine.

    The context contains only engine lifecycle information. Runtime
    services themselves remain owned by ExecutionRuntime.
    """

    status: EngineStatus = EngineStatus.STOPPED
    mode: EngineMode = EngineMode.PAPER
    account_id: UUID | None = None


class AQEEngine:
    """
    Top-level lifecycle coordinator for the Athena Quant Engine.

    The engine owns the runtime lifecycle:

        START
          |
          v
        Broker
          |
          v
        Market Data
          |
          v
        Strategies
          |
          v
        Risk -> Execution
          |
          v
        RUNNING

    The engine does not implement broker execution, risk evaluation,
    strategy logic, or market-data processing itself. It only starts,
    stops, pauses, and exposes the state of those components.
    """

    def __init__(
        self,
        *,
        runtime_factory: ExecutionRuntimeFactory | None = None,
        mode: EngineMode | None = None,
    ) -> None:
        self.context = EngineContext(
            mode=mode or self._resolve_mode(),
        )

        self.runtime_factory = runtime_factory or ExecutionRuntimeFactory()

        self._runtime: ExecutionRuntime | None = None

        self._broker_connected = False

        self._paused_strategy_ids: set[str] = set()

        logger.info(
            "AQE engine initialized. mode=%s status=%s",
            self.context.mode.value,
            self.context.status.value,
        )

    # ==================================================================
    # PUBLIC LIFECYCLE
    # ==================================================================

    async def start(self, account_id: UUID) -> None:
        """
        Start the complete AQE trading runtime.

        Startup order:

            1. Resolve runtime
            2. Connect broker
            3. Start market-data consumer
            4. Start live tick hub
            5. Reconcile market-data subscriptions
            6. Start historical synchronization
            7. Start strategies
            8. Start risk -> execution pipeline
            9. Mark engine RUNNING
        """

        if self.context.status is not EngineStatus.STOPPED:
            raise EngineStateError(
                "AQE engine can only be started from STOPPED state. "
                f"Current state={self.context.status.value}."
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
            # Resolve runtime
            # ----------------------------------------------------------

            self._runtime = await self.runtime_factory.create(account_id)

            # ----------------------------------------------------------
            # Broker
            # ----------------------------------------------------------

            await self._start_broker()

            # ----------------------------------------------------------
            # Market data
            # ----------------------------------------------------------

            await self._start_market_data()

            # ----------------------------------------------------------
            # Strategies
            # ----------------------------------------------------------

            await self._start_strategy_runtime()

            # ----------------------------------------------------------
            # Risk -> Execution pipeline
            # ----------------------------------------------------------

            await self._start_signal_pipeline()

            self.context.status = EngineStatus.RUNNING

            logger.info(
                "AQE engine started successfully. account_id=%s mode=%s",
                account_id,
                self.context.mode.value,
            )

        except Exception:
            logger.exception(
                "AQE engine failed to start. account_id=%s",
                account_id,
            )

            await self._cleanup_failed_start()

            self.context.status = EngineStatus.STOPPED
            self.context.account_id = None
            self._paused_strategy_ids.clear()

            raise

    async def stop(self) -> None:
        """
        Stop the complete AQE runtime.

        Shutdown is performed in reverse dependency order:

            Risk -> Execution
            Strategies
            Historical Data
            Live Tick Hub
            Market Data Consumer
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

        try:
            await self._stop_signal_pipeline()
            await self._stop_strategy_runtime()
            await self._stop_market_data()
            await self._stop_broker()

        finally:
            self._runtime = None
            self._broker_connected = False
            self._paused_strategy_ids.clear()

            self.context.status = EngineStatus.STOPPED
            self.context.account_id = None

            logger.info("AQE engine stopped.")

    async def pause(self) -> None:
        """
        Pause all running LIVE/PAPER strategies while keeping the
        AQE runtime itself active.

        Broker, market-data services, historical synchronization,
        and the Risk -> Execution pipeline remain running.

        Only strategies that were actively RUNNING when the engine
        was paused are recorded for subsequent resume.
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

        except Exception:
            logger.exception(
                "Failed to pause AQE strategy runtime. "
                "Restoring strategies already paused by engine."
            )

            await self._resume_paused_strategies()

            self._paused_strategy_ids.clear()

            raise

        self.context.status = EngineStatus.PAUSED

        logger.info(
            "AQE engine paused. paused_strategy_ids=%s",
            sorted(self._paused_strategy_ids),
        )

    async def resume(self) -> None:
        """
        Resume only the strategies that were paused by AQEEngine.pause().

        Strategies that were already paused before the engine pause
        remain paused.
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

        except Exception:
            logger.exception("Failed to resume one or more AQE strategies.")
            raise

        self._paused_strategy_ids.clear()

        self.context.status = EngineStatus.RUNNING

        logger.info("AQE engine resumed.")

    # ==================================================================
    # STARTUP
    # ==================================================================

    async def _start_broker(self) -> None:
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

        await runtime.broker_manager.connect(
            runtime.account.broker_credentials,
        )

        self._broker_connected = True

        logger.info(
            "Broker connected. broker=%s account_id=%s",
            runtime.account.broker,
            runtime.account.account_id,
        )

    async def _start_market_data(self) -> None:
        runtime = self._require_runtime()

        consumer = runtime.market_data_consumer

        if consumer is not None:
            await consumer.start()

        hub = runtime.live_tick_hub

        if hub is not None:
            await hub.start()

        subscription_manager = runtime.market_data_subscription_manager

        if subscription_manager is not None:
            await subscription_manager.reconcile()

        historical_synchronizer = runtime.historical_data_synchronizer

        if historical_synchronizer is not None:
            await historical_synchronizer.start()

        logger.info("AQE market-data runtime started.")

    async def _start_strategy_runtime(self) -> None:
        runtime = self._require_runtime()

        strategy_manager = runtime.strategy_manager

        if strategy_manager is None:
            logger.warning(
                "No strategy manager configured. " "AQE will run without strategies."
            )
            return

        await strategy_manager.start()

        logger.info("AQE strategy runtime started.")

    async def _start_signal_pipeline(self) -> None:
        runtime = self._require_runtime()

        pipeline = runtime.live_pipeline

        if pipeline is None:
            logger.warning(
                "No live signal pipeline configured. "
                "Risk -> Execution will not process strategy signals."
            )
            return

        await pipeline.start()

        logger.info("AQE risk -> execution pipeline started.")

    # ==================================================================
    # SHUTDOWN
    # ==================================================================

    async def _stop_signal_pipeline(self) -> None:
        runtime = self._runtime

        if runtime is None:
            return

        pipeline = runtime.live_pipeline

        if pipeline is None:
            return

        try:
            await pipeline.stop()

        except Exception:
            logger.exception("Failed to stop AQE risk -> execution pipeline.")

    async def _stop_strategy_runtime(self) -> None:
        runtime = self._runtime

        if runtime is None:
            return

        strategy_manager = runtime.strategy_manager

        if strategy_manager is None:
            return

        try:
            await strategy_manager.stop()

        except Exception:
            logger.exception("Failed to stop AQE strategy runtime.")

    async def _stop_market_data(self) -> None:
        runtime = self._runtime

        if runtime is None:
            return

        historical_synchronizer = runtime.historical_data_synchronizer

        if historical_synchronizer is not None:
            try:
                await historical_synchronizer.stop()

            except Exception:
                logger.exception("Failed to stop historical-data synchronizer.")

        hub = runtime.live_tick_hub

        if hub is not None:
            try:
                await hub.stop()

            except Exception:
                logger.exception("Failed to stop live tick hub.")

        consumer = runtime.market_data_consumer

        if consumer is not None:
            try:
                await consumer.stop()

            except Exception:
                logger.exception("Failed to stop market-data consumer.")

    async def _stop_broker(self) -> None:
        runtime = self._runtime

        if runtime is None:
            return

        if not self._broker_connected:
            return

        try:
            await runtime.broker_manager.disconnect()

        except Exception:
            logger.exception("Failed to disconnect broker.")

        finally:
            self._broker_connected = False

    async def _cleanup_failed_start(self) -> None:
        """
        Best-effort cleanup after startup failure.

        This deliberately mirrors shutdown order but does not change the
        externally visible engine state until the caller resets it.
        """

        try:
            await self._stop_signal_pipeline()
        except Exception:
            logger.exception("Startup cleanup failed while stopping signal pipeline.")

        try:
            await self._stop_strategy_runtime()
        except Exception:
            logger.exception("Startup cleanup failed while stopping strategies.")

        try:
            await self._stop_market_data()
        except Exception:
            logger.exception("Startup cleanup failed while stopping market data.")

        try:
            await self._stop_broker()
        except Exception:
            logger.exception("Startup cleanup failed while stopping broker.")

        self._runtime = None
        self._broker_connected = False
        self._paused_strategy_ids.clear()

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(self) -> dict[str, Any]:
        """
        Return the complete current AQE runtime state.

        Every component is queried using its actual lifecycle contract.
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

        return {
            "status": self.context.status.value,
            "mode": self.context.mode.value,
            "account": account_snapshot,
            "broker": {
                "required": self._requires_broker,
                "connected": self._broker_connected,
            },
            "market_data": {
                "consumer_running": self._market_data_consumer_running(),
                "live_tick_hub_running": self._live_tick_hub_running(),
                "historical_sync_running": self._historical_sync_running(),
            },
            "strategies": {
                "configured": self.strategy_manager is not None,
                "running": self._strategy_manager_running(),
                "paused_strategy_ids": self._paused_strategy_ids_snapshot(),
            },
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
        return self._runtime

    @property
    def broker_manager(self):
        runtime = self._runtime
        return runtime.broker_manager if runtime is not None else None

    @property
    def market_data_consumer(self) -> MarketDataConsumer | None:
        runtime = self._runtime
        return runtime.market_data_consumer if runtime is not None else None

    @property
    def live_tick_hub(self) -> LiveTickHub | None:
        runtime = self._runtime
        return runtime.live_tick_hub if runtime is not None else None

    @property
    def market_data_subscription_manager(
        self,
    ) -> MarketDataSubscriptionManager | None:
        runtime = self._runtime
        return runtime.market_data_subscription_manager if runtime is not None else None

    @property
    def historical_synchronizer(
        self,
    ) -> HistoricalDataSynchronizer | None:
        runtime = self._runtime
        return runtime.historical_data_synchronizer if runtime is not None else None

    @property
    def historical_data_service(
        self,
    ) -> HistoricalDataService | None:
        runtime = self._runtime
        return runtime.historical_data_service if runtime is not None else None

    @property
    def market_data_service(
        self,
    ) -> MarketDataService | None:
        runtime = self._runtime
        return runtime.market_data_service if runtime is not None else None

    @property
    def strategy_manager(self):
        runtime = self._runtime
        return runtime.strategy_manager if runtime is not None else None

    @property
    def live_pipeline(self):
        runtime = self._runtime
        return runtime.live_pipeline if runtime is not None else None

    @property
    def execution_engine(self):
        runtime = self._runtime
        return runtime.execution_engine if runtime is not None else None

    # ==================================================================
    # COMPONENT STATE
    # ==================================================================

    def _market_data_consumer_running(self) -> bool:
        consumer = self.market_data_consumer

        if consumer is None:
            return False

        try:
            status = consumer.status()
        except Exception:
            logger.exception("Failed to read market-data consumer status.")
            return False

        return bool(status.get("running", False))

    def _live_tick_hub_running(self) -> bool:
        hub = self.live_tick_hub

        if hub is None:
            return False

        # LiveTickHub intentionally exposes its lifecycle internally
        # through _started and currently has no public status property.
        return bool(getattr(hub, "_started", False))

    def _historical_sync_running(self) -> bool:
        synchronizer = self.historical_synchronizer

        if synchronizer is None:
            return False

        # HistoricalDataSynchronizer currently exposes _running as its
        # lifecycle flag and has no public status property.
        return bool(getattr(synchronizer, "_running", False))

    def _strategy_manager_running(self) -> bool:
        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            return False

        running = getattr(strategy_manager, "running", None)

        if running is not None:
            return bool(running)

        is_running = getattr(strategy_manager, "is_running", None)

        if is_running is not None:
            return bool(is_running)

        return False

    def _live_pipeline_running(self) -> bool:
        pipeline = self.live_pipeline

        if pipeline is None:
            return False

        # LivePipeline's actual public lifecycle property is `started`.
        started = getattr(pipeline, "started", None)

        if started is not None:
            return bool(started)

        # Compatibility with any future implementation exposing one of
        # the more conventional lifecycle names.
        running = getattr(pipeline, "running", None)

        if running is not None:
            return bool(running)

        is_running = getattr(pipeline, "is_running", None)

        if is_running is not None:
            return bool(is_running)

        return False

    def _paused_strategy_ids_snapshot(self) -> list[str]:
        """
        Return the strategy IDs that AQEEngine itself paused.

        This intentionally does not ask StrategyManager for a
        `paused_strategy_ids` property because StrategyManager does not
        expose such a property.
        """

        return sorted(self._paused_strategy_ids)

    async def _resume_paused_strategies(self) -> None:
        """
        Resume strategies previously paused by AQEEngine.

        If a strategy was removed while the engine was paused, it is
        simply skipped.
        """

        strategy_manager = self.strategy_manager

        if strategy_manager is None:
            raise EngineStateError(
                "Cannot resume AQE strategies because the strategy manager "
                "is not configured."
            )

        strategy_ids = tuple(self._paused_strategy_ids)

        for strategy_id in strategy_ids:
            instance = strategy_manager.get(strategy_id)

            if instance is None:
                logger.warning(
                    "Strategy instance no longer exists while resuming: " "id=%s",
                    strategy_id,
                )
                continue

            if instance.status is not StrategyStatus.PAUSED:
                logger.info(
                    "Skipping strategy resume because strategy is no "
                    "longer paused: id=%s status=%s",
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
        return self.context.mode in {
            EngineMode.LIVE,
            EngineMode.PAPER,
        }

    @staticmethod
    def _resolve_mode() -> EngineMode:
        """
        Resolve the configured engine mode.

        Invalid configuration falls back to PAPER rather than preventing
        the backend application from starting.
        """

        raw_mode = getattr(settings, "AQE_ENGINE_MODE", None)

        if raw_mode is None:
            raw_mode = getattr(settings, "ENGINE_MODE", None)

        if raw_mode is None:
            return EngineMode.PAPER

        if isinstance(raw_mode, EngineMode):
            return raw_mode

        try:
            return EngineMode(str(raw_mode).strip().upper())

        except ValueError:
            logger.warning(
                "Invalid AQE engine mode %r. Falling back to PAPER.",
                raw_mode,
            )
            return EngineMode.PAPER

    def _require_runtime(self) -> ExecutionRuntime:
        runtime = self._runtime

        if runtime is None:
            raise EngineStateError("AQE runtime has not been created.")

        return runtime


# ======================================================================
# GLOBAL ENGINE
# ======================================================================

_aqe_engine = AQEEngine()


def get_aqe_engine() -> AQEEngine:
    """
    Return the application-wide AQE engine instance.
    """

    return _aqe_engine
