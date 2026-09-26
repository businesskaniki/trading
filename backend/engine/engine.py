from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.market_data.consumer import MarketDataConsumer
from app.market_data.historical_synchronizer import HistoricalDataSynchronizer
from app.market_data.live import LiveTickHub
from app.market_data.service import MarketDataService
from app.market_data.subscription_manager import MarketDataSubscriptionManager
from execution.live_pipeline import LivePipeline
from execution.runtime_account import RuntimeAccountResolver
from risk.engine import RiskEngine
from strategies.runtime.manager import StrategyManager

from .config import EngineConfig
from .context import EngineContext
from .enums import EngineMode, EngineStatus
from .exceptions import (
    EnginePauseError,
    EngineResumeError,
    EngineShutdownError,
    EngineStartupError,
    EngineStateError,
)

logger = logging.getLogger(__name__)


class AQEEngine:
    """
    Top-level lifecycle coordinator for the Athena Quant Engine.

    Runtime flow:

        Market Data
            ↓
        Event Bus
            ↓
        Strategy Runtime
            ↓
        Strategy Signal
            ↓
        Risk Context
            ↓
        Risk Engine
            ↓
        Execution Engine
            ↓
        Broker
            ↓
        MT5 / Paper Broker

    The AQE Engine owns lifecycle orchestration only.

    It does not implement:

        - strategy logic
        - risk calculations
        - order execution logic
        - broker-specific logic
        - market-data normalization
        - database persistence
        - credential encryption/decryption

    Account resolution and credential decryption are delegated to
    RuntimeAccountResolver.
    """

    def __init__(
        self,
        *,
        broker_manager: BrokerManager,
        market_data_service: MarketDataService,
        market_data_consumer: MarketDataConsumer,
        market_data_subscription_manager: MarketDataSubscriptionManager,
        historical_data_synchronizer: HistoricalDataSynchronizer,
        live_tick_hub: LiveTickHub,
        strategy_manager: StrategyManager,
        risk_engine: RiskEngine,
        live_pipeline: LivePipeline | None = None,
        runtime_account_resolver: RuntimeAccountResolver | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        self.broker_manager = broker_manager
        self.market_data_service = market_data_service
        self.market_data_consumer = market_data_consumer
        self.market_data_subscription_manager = market_data_subscription_manager
        self.historical_data_synchronizer = historical_data_synchronizer
        self.live_tick_hub = live_tick_hub
        self.strategy_manager = strategy_manager
        self.risk_engine = risk_engine
        self.live_pipeline = live_pipeline
        self.runtime_account_resolver = runtime_account_resolver

        self.context = EngineContext(
            config=config or EngineConfig(),
        )

        self._broker_connected = False
        self._paused_strategy_ids: set[str] = set()
        self._account_id: UUID | None = None

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(
        self,
        *,
        account_id: UUID | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> None:
        """
        Start the AQE runtime.

        LIVE / PAPER startup:

            1. Resolve runtime account and credentials
            2. Broker
            3. Market-data consumer
            4. Live tick hub
            5. Market-data subscriptions
            6. Historical synchronizer
            7. Strategy runtime
            8. Signal → Risk → Execution pipeline
            9. RUNNING

        Credentials are resolved at startup and passed directly to the
        broker manager. They are never stored in EngineContext or the
        engine snapshot.

        ``credentials`` remains supported for trusted internal callers,
        but normal application startup should provide ``account_id`` and
        let RuntimeAccountResolver obtain the credentials.
        """

        if self.context.status in {
            EngineStatus.RUNNING,
            EngineStatus.STARTING,
            EngineStatus.RESUMING,
        }:
            raise EngineStateError(
                "Cannot start engine while status is " f"{self.context.status.value}."
            )

        if self.context.status is EngineStatus.PAUSED:
            raise EngineStateError("Engine is paused. Use resume() instead of start().")

        self._validate_mode_before_start()

        if self._requires_broker:
            self._validate_account_startup(account_id, credentials)

        self.context.status = EngineStatus.STARTING
        self.context.clear_error()

        logger.info(
            "Starting AQE Engine. mode=%s account_id=%s",
            self.context.mode.value,
            account_id,
        )

        try:
            if self._requires_broker:
                await self._start_broker(
                    account_id=account_id,
                    credentials=credentials,
                )

            await self._start_market_data()

            await self._start_strategy_runtime()

            await self._start_signal_pipeline()

            self.context.status = EngineStatus.RUNNING
            self.context.started_at = self._utc_now()
            self.context.resumed_at = None

            logger.info(
                "AQE Engine started successfully. mode=%s account_id=%s",
                self.context.mode.value,
                self._account_id,
            )

        except Exception as exc:
            self.context.set_error(exc)
            self.context.status = EngineStatus.ERROR

            logger.exception("AQE Engine startup failed.")

            await self._rollback_startup()

            raise EngineStartupError(f"AQE Engine failed to start: {exc}") from exc

    async def pause(self) -> None:
        """
        Pause strategy generation while keeping runtime infrastructure
        alive.

        Market data continues running.

        The signal → risk → execution pipeline remains subscribed,
        but strategies are paused so no new strategy signals are
        generated.
        """

        if self.context.status is EngineStatus.PAUSED:
            return

        if self.context.status is not EngineStatus.RUNNING:
            raise EngineStateError(
                "Engine can only be paused while RUNNING. "
                f"Current status: {self.context.status.value}."
            )

        self.context.status = EngineStatus.PAUSING

        logger.info("Pausing AQE Engine strategy execution.")

        try:
            self._paused_strategy_ids.clear()

            if self.context.config.pause_strategies_on_pause:
                for instance in self.strategy_manager.instances():
                    strategy_id = instance.strategy_id

                    status = getattr(
                        instance,
                        "status",
                        None,
                    )

                    status_value = getattr(
                        status,
                        "value",
                        status,
                    )

                    if status_value in {
                        "RUNNING",
                        "RESUMING",
                    }:
                        await self.strategy_manager.pause_instance(
                            strategy_id,
                        )

                        self._paused_strategy_ids.add(strategy_id)

            self.context.paused_at = self._utc_now()
            self.context.status = EngineStatus.PAUSED

            logger.info(
                "AQE Engine paused. strategies_paused=%s",
                len(self._paused_strategy_ids),
            )

        except Exception as exc:
            self.context.set_error(exc)
            self.context.status = EngineStatus.ERROR

            logger.exception("Failed to pause AQE Engine.")

            raise EnginePauseError(f"Failed to pause AQE Engine: {exc}") from exc

    async def resume(self) -> None:
        """
        Resume strategies that were running before pause.
        """

        if self.context.status is EngineStatus.RUNNING:
            return

        if self.context.status is not EngineStatus.PAUSED:
            raise EngineStateError(
                "Engine can only be resumed while PAUSED. "
                f"Current status: {self.context.status.value}."
            )

        self.context.status = EngineStatus.RESUMING

        logger.info("Resuming AQE Engine.")

        try:
            if self._requires_broker:
                await self._verify_broker()

                if self.context.config.auto_reconcile_market_data:
                    await self.market_data_subscription_manager.reconcile()

            if self.context.config.resume_strategies_on_resume:
                for strategy_id in list(
                    self._paused_strategy_ids,
                ):
                    await self.strategy_manager.resume_instance(
                        strategy_id,
                    )

            self.context.resumed_at = self._utc_now()
            self.context.status = EngineStatus.RUNNING

            logger.info("AQE Engine resumed successfully.")

        except Exception as exc:
            self.context.set_error(exc)
            self.context.status = EngineStatus.ERROR

            logger.exception("Failed to resume AQE Engine.")

            raise EngineResumeError(f"Failed to resume AQE Engine: {exc}") from exc

    async def stop(self) -> None:
        """
        Stop the complete AQE runtime.

        Shutdown order:

            1. Stop strategy signal intake
            2. Stop strategies
            3. Historical synchronizer
            4. Live tick hub
            5. Market-data consumer
            6. Broker
        """

        if self.context.status is EngineStatus.STOPPED:
            return

        if self.context.status is EngineStatus.STOPPING:
            return

        self.context.status = EngineStatus.STOPPING

        logger.info("Stopping AQE Engine.")

        errors: list[Exception] = []

        # --------------------------------------------------------------
        # Signal → Risk → Execution pipeline
        # --------------------------------------------------------------

        try:
            await self._stop_signal_pipeline()
        except Exception as exc:
            errors.append(exc)
            logger.exception(
                "Failed to stop signal/risk/execution pipeline.",
            )

        # --------------------------------------------------------------
        # Strategy runtime
        # --------------------------------------------------------------

        try:
            await self.strategy_manager.stop()
        except Exception as exc:
            errors.append(exc)
            logger.exception(
                "Failed to stop strategy runtime.",
            )

        # --------------------------------------------------------------
        # Historical synchronizer
        # --------------------------------------------------------------

        try:
            await self.historical_data_synchronizer.stop()
        except Exception as exc:
            errors.append(exc)
            logger.exception(
                "Failed to stop historical-data synchronizer.",
            )

        # --------------------------------------------------------------
        # Live tick hub
        # --------------------------------------------------------------

        try:
            await self.live_tick_hub.stop()
        except Exception as exc:
            errors.append(exc)
            logger.exception(
                "Failed to stop live tick hub.",
            )

        # --------------------------------------------------------------
        # Redis market-data consumer
        # --------------------------------------------------------------

        try:
            await self.market_data_consumer.stop()
        except Exception as exc:
            errors.append(exc)
            logger.exception(
                "Failed to stop market-data consumer.",
            )

        # --------------------------------------------------------------
        # Broker
        # --------------------------------------------------------------

        if self._broker_connected and self.context.config.disconnect_broker_on_stop:
            try:
                await self.broker_manager.disconnect()
            except Exception as exc:
                errors.append(exc)
                logger.exception(
                    "Failed to disconnect broker.",
                )
            finally:
                self._broker_connected = False

        # --------------------------------------------------------------
        # Final state
        # --------------------------------------------------------------

        self.context.stopped_at = self._utc_now()
        self._paused_strategy_ids.clear()
        self._account_id = None

        if errors:
            error = EngineShutdownError(
                "AQE Engine shutdown completed with " f"{len(errors)} error(s)."
            )

            self.context.set_error(error)
            self.context.status = EngineStatus.ERROR

            raise error

        self.context.status = EngineStatus.STOPPED
        self.context.clear_error()

        logger.info("AQE Engine stopped successfully.")

    # ==================================================================
    # STARTUP
    # ==================================================================

    async def _start_broker(
        self,
        *,
        account_id: UUID | None,
        credentials: dict[str, Any] | None,
    ) -> None:
        """
        Establish the broker connection.

        Normal runtime path:

            account_id
                ↓
            RuntimeAccountResolver
                ↓
            RuntimeAccount.broker_credentials
                ↓
            BrokerManager.connect()

        The decrypted password is never retained by AQEEngine.
        """

        if self._broker_connected:
            return

        resolved_credentials = credentials

        if resolved_credentials is None:
            if account_id is None:
                raise EngineStartupError(
                    "An account_id is required to start LIVE/PAPER " "execution."
                )

            if self.runtime_account_resolver is None:
                raise EngineStartupError(
                    "RuntimeAccountResolver is required when broker "
                    "credentials are resolved from a trading account."
                )

            runtime_account = await self.runtime_account_resolver.resolve(
                account_id,
            )

            self._account_id = runtime_account.account_id

            resolved_credentials = runtime_account.broker_credentials

        else:
            self._account_id = account_id

        await self.broker_manager.connect(
            resolved_credentials,
        )

        self._broker_connected = True

        logger.info(
            "Broker connection established. account_id=%s",
            self._account_id,
        )

    async def _start_market_data(self) -> None:
        """
        Start market-data infrastructure.
        """

        # --------------------------------------------------------------
        # Redis → EventBus
        # --------------------------------------------------------------

        consumer_status = self.market_data_consumer.status()

        if not bool(
            consumer_status.get(
                "running",
                False,
            )
        ):
            await self.market_data_consumer.start()

        # --------------------------------------------------------------
        # EventBus → WebSocket clients
        # --------------------------------------------------------------

        if self.context.config.start_live_tick_hub:
            if not self._live_tick_hub_running:
                await self.live_tick_hub.start()

        # --------------------------------------------------------------
        # Broker symbol subscriptions
        # --------------------------------------------------------------

        if self.context.config.auto_reconcile_market_data:
            await self.market_data_subscription_manager.reconcile()

        # --------------------------------------------------------------
        # Historical synchronization
        # --------------------------------------------------------------

        if self.context.config.start_historical_synchronizer:
            if not self._historical_sync_running:
                await self.historical_data_synchronizer.start()

        logger.info("Market-data runtime started.")

    async def _start_strategy_runtime(self) -> None:
        """
        Start the strategy runtime infrastructure.

        Strategy instances remain controlled by StrategyManager.
        """

        if not self.strategy_manager.running:
            await self.strategy_manager.start()

        logger.info("Strategy runtime started.")

    async def _start_signal_pipeline(self) -> None:
        """
        Start the strategy signal → risk → execution pipeline.

        Without this subscription, strategies can generate signals but
        those signals never reach the Risk Engine or Execution Engine.
        """

        if self.live_pipeline is None:
            raise EngineStartupError(
                "AQE Engine requires a LivePipeline for " "LIVE/PAPER execution."
            )

        if not self.live_pipeline.started:
            await self.live_pipeline.start()

        logger.info(
            "Signal → Risk → Execution pipeline started.",
        )

    async def _stop_signal_pipeline(self) -> None:
        """
        Stop the signal → risk → execution pipeline.
        """

        if self.live_pipeline is None:
            return

        if self.live_pipeline.started:
            await self.live_pipeline.stop()

        logger.info(
            "Signal → Risk → Execution pipeline stopped.",
        )

    async def _rollback_startup(self) -> None:
        """
        Best-effort rollback after startup failure.
        """

        logger.warning(
            "Rolling back partially started AQE Engine.",
        )

        try:
            await self._stop_signal_pipeline()
        except Exception:
            logger.exception(
                "Startup rollback failed while stopping "
                "signal/risk/execution pipeline.",
            )

        try:
            await self.strategy_manager.stop()
        except Exception:
            logger.exception(
                "Startup rollback failed while stopping strategies.",
            )

        try:
            await self.historical_data_synchronizer.stop()
        except Exception:
            logger.exception(
                "Startup rollback failed while stopping " "historical synchronizer.",
            )

        try:
            await self.live_tick_hub.stop()
        except Exception:
            logger.exception(
                "Startup rollback failed while stopping " "live tick hub.",
            )

        try:
            await self.market_data_consumer.stop()
        except Exception:
            logger.exception(
                "Startup rollback failed while stopping " "market-data consumer.",
            )

        if self._broker_connected:
            try:
                await self.broker_manager.disconnect()
            except Exception:
                logger.exception(
                    "Startup rollback failed while " "disconnecting broker.",
                )
            finally:
                self._broker_connected = False

        self._account_id = None

    # ==================================================================
    # HEALTH / STATUS
    # ==================================================================

    async def _verify_broker(self) -> None:
        """
        Verify that the broker connection is still available.
        """

        status = await self.broker_manager.connection_status()

        if isinstance(status, bool):
            connected = status

        elif isinstance(status, dict):
            connected = bool(
                status.get(
                    "connected",
                    False,
                )
            )

        else:
            connected_value = getattr(
                status,
                "connected",
                None,
            )

            if connected_value is not None:
                connected = bool(connected_value)
            else:
                connected = str(status).lower() in {
                    "connected",
                    "true",
                    "1",
                }

        if not connected:
            raise EngineResumeError(
                "Broker connection is not available.",
            )

        self._broker_connected = True

    def snapshot(self) -> dict[str, Any]:
        """
        Return a safe runtime snapshot.

        No broker credentials or secrets are exposed.
        """

        consumer_status = self.market_data_consumer.status()

        strategy_instances = self.strategy_manager.instances()

        return {
            "status": self.context.status.value,
            "mode": self.context.mode.value,
            "created_at": self._iso(
                self.context.created_at,
            ),
            "started_at": self._iso(
                self.context.started_at,
            ),
            "paused_at": self._iso(
                self.context.paused_at,
            ),
            "resumed_at": self._iso(
                self.context.resumed_at,
            ),
            "stopped_at": self._iso(
                self.context.stopped_at,
            ),
            "last_error": self.context.last_error,
            "account_id": (
                str(self._account_id) if self._account_id is not None else None
            ),
            "broker": {
                "required": self._requires_broker,
                "connected": self._broker_connected,
            },
            "market_data": {
                "redis_consumer": consumer_status,
                "live_tick_hub": {
                    "running": self._live_tick_hub_running,
                },
                "historical_synchronizer": {
                    "running": self._historical_sync_running,
                },
            },
            "strategies": {
                "manager_running": self.strategy_manager.running,
                "instance_count": len(strategy_instances),
                "instances": self.strategy_manager.snapshots(),
            },
            "pipeline": {
                "signal_risk_execution": (
                    self.live_pipeline.snapshot()
                    if self.live_pipeline is not None
                    else None
                ),
            },
        }

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def _requires_broker(self) -> bool:
        """
        Return whether the current engine mode requires a broker.

        LIVE:
            Real broker execution.

        PAPER:
            Paper broker execution through BrokerManager.

        BACKTEST / REPLAY:
            No live broker connection.
        """

        return self.context.mode in {
            EngineMode.LIVE,
            EngineMode.PAPER,
        }

    @property
    def _live_tick_hub_running(self) -> bool:
        """
        Safely determine whether the live tick hub is running.
        """

        running = getattr(
            self.live_tick_hub,
            "running",
            None,
        )

        if running is not None:
            return bool(running)

        status = getattr(
            self.live_tick_hub,
            "status",
            None,
        )

        if callable(status):
            try:
                value = status()

                if isinstance(value, dict):
                    return bool(
                        value.get(
                            "running",
                            False,
                        )
                    )

                return bool(value)

            except Exception:
                return False

        return bool(
            getattr(
                self.live_tick_hub,
                "_started",
                False,
            )
        )

    @property
    def _historical_sync_running(self) -> bool:
        """
        Safely determine whether the historical synchronizer is running.
        """

        running = getattr(
            self.historical_data_synchronizer,
            "running",
            None,
        )

        if running is not None:
            return bool(running)

        status = getattr(
            self.historical_data_synchronizer,
            "status",
            None,
        )

        if callable(status):
            try:
                value = status()

                if isinstance(value, dict):
                    return bool(
                        value.get(
                            "running",
                            False,
                        )
                    )

                return bool(value)

            except Exception:
                return False

        return bool(
            getattr(
                self.historical_data_synchronizer,
                "_running",
                False,
            )
        )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def _validate_account_startup(
        self,
        account_id: UUID | None,
        credentials: dict[str, Any] | None,
    ) -> None:
        """
        Validate broker startup inputs.

        Normal application startup uses account_id.

        Direct credentials are retained only as a trusted internal
        compatibility path.
        """

        if account_id is None and credentials is None:
            raise EngineStateError(
                "An account_id is required to start LIVE/PAPER " "execution."
            )

        if account_id is not None:
            if self.runtime_account_resolver is None:
                raise EngineStateError(
                    "RuntimeAccountResolver is required for "
                    "account-based engine startup."
                )

    def _validate_mode_before_start(self) -> None:
        """
        Validate that the requested mode has the runtime dependencies
        required by this engine.
        """

        if self.context.mode in {
            EngineMode.BACKTEST,
            EngineMode.REPLAY,
        }:
            raise EngineStateError(
                f"Engine mode {self.context.mode.value} is not yet "
                "wired to a dedicated backtest/replay runtime."
            )

        if (
            self.context.mode
            in {
                EngineMode.LIVE,
                EngineMode.PAPER,
            }
            and self.live_pipeline is None
        ):
            raise EngineStateError("LIVE/PAPER engine requires a LivePipeline.")

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(
        value: datetime | None,
    ) -> str | None:
        if value is None:
            return None

        return value.isoformat()
