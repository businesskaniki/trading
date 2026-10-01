"""Strategy instance lifecycle management for the AQE Strategy Engine."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..bootstrap import StrategyBootstrap, strategy_bootstrap
from ..core import StrategyConfig, StrategyMode, StrategyStatus
from ..core.exceptions import StrategyStateError
from .account_router import StrategyAccountRouter
from .dispatcher import StrategyDispatcher
from .instance import StrategyInstance
from .signal_publisher import (
    BacktestSignalPublisher,
    SignalPublisher,
    StrategySignalPublisher,
)

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    Manage the runtime lifecycle of AQE strategy instances.

    The manager is the primary orchestration layer for configured
    strategy instances.

    Responsibilities:
        - bootstrap strategy implementations
        - create strategy instances
        - register instances with the dispatcher
        - assign LIVE/PAPER strategies to accounts
        - initialize strategies
        - activate/deactivate strategies
        - start/stop strategy lifecycles
        - pause/resume strategies
        - remove strategy instances
        - expose runtime state
        - inject shared runtime dependencies

    The manager does NOT:
        - consume Redis directly
        - communicate with MT5
        - communicate with brokers
        - perform risk checks
        - calculate position sizing
        - execute orders
        - persist trading data

    Runtime architecture:

        StrategyRegistry
              │
              ▼
        StrategyManager
              │
              ├── StrategyInstance
              │       │
              │       └── BaseStrategy
              │
              └── StrategyDispatcher
                      │
                      ▼
                Market Events

    Activation and lifecycle are deliberately separate.

        enabled=False
            means the strategy is administratively disabled.

        status=RUNNING
            means its lifecycle is running.

        is_active
            means enabled=True AND lifecycle is READY/RUNNING.

    Therefore a strategy can legitimately be:

        enabled=False + RUNNING

    In that state it remains initialized/running but ignores market
    data. This allows administrative activation/deactivation without
    destroying strategy state.
    """

    def __init__(
        self,
        dispatcher: StrategyDispatcher | None = None,
        signal_publisher: SignalPublisher | None = None,
        bootstrap: StrategyBootstrap | None = None,
        account_router: StrategyAccountRouter | None = None,
    ) -> None:
        """Initialize the strategy manager."""

        self._dispatcher = dispatcher or StrategyDispatcher()

        self._signal_publisher = signal_publisher or StrategySignalPublisher()

        self._backtest_signal_publisher = BacktestSignalPublisher()

        self._bootstrap = bootstrap or strategy_bootstrap

        self._account_router = account_router or StrategyAccountRouter()

        self._lock = asyncio.Lock()

        self._running = False

        # The manager and dispatcher have separate lifecycle concerns.
        #
        # A manager can be running before any LIVE/PAPER strategy exists.
        # The dispatcher is therefore started lazily when the first
        # LIVE/PAPER strategy is created.
        self._dispatcher_running = False

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def dispatcher(self) -> StrategyDispatcher:
        """Return the strategy dispatcher."""

        return self._dispatcher

    @property
    def signal_publisher(self) -> SignalPublisher:
        """Return the shared LIVE/PAPER signal publisher."""

        return self._signal_publisher

    @property
    def bootstrap(self) -> StrategyBootstrap:
        """Return the strategy bootstrap service."""

        return self._bootstrap

    @property
    def account_router(self) -> StrategyAccountRouter:
        """Return the strategy-to-account router."""

        return self._account_router

    @property
    def running(self) -> bool:
        """Return whether the strategy manager is running."""

        return self._running

    @property
    def dispatcher_running(self) -> bool:
        """Return whether the market-event dispatcher is running."""

        return self._dispatcher_running

    @property
    def instance_count(self) -> int:
        """Return the number of managed strategy instances."""

        return self._dispatcher.instance_count

    @property
    def active_instance_count(self) -> int:
        """Return the number of currently active strategy instances."""

        return len(self.active_instances())

    # ==================================================================
    # MANAGER LIFECYCLE
    # ==================================================================

    async def start(self) -> None:
        """
        Start the strategy runtime infrastructure.

        This method:

            1. bootstraps registered strategy implementations
            2. marks the manager as running

        The dispatcher is intentionally started lazily when a LIVE/PAPER
        strategy instance is created.

        This allows:

            manager.start()
                -> no live strategies yet
                -> dispatcher remains stopped

        followed by:

            create(LIVE/PAPER strategy)
                -> dispatcher starts
                -> strategy can receive market events

        BACKTEST/REPLAY runtimes do not require the live market-event
        dispatcher.
        """

        async with self._lock:
            if self._running:
                return

            await self._bootstrap.start()

            self._running = True

        logger.info(
            "Strategy manager started: instances=%s active=%s",
            self.instance_count,
            self.active_instance_count,
        )

    async def stop(self) -> None:
        """
        Stop the strategy runtime.

        Existing strategy instances are stopped before the dispatcher
        shuts down.
        """

        async with self._lock:
            if not self._running:
                return

            instances = self._dispatcher.instances()

            for instance in instances:
                try:
                    if instance.status not in {
                        StrategyStatus.STOPPED,
                        StrategyStatus.CREATED,
                    }:
                        await instance.stop()

                except Exception:
                    logger.exception(
                        "Failed to stop strategy instance: id=%s",
                        instance.strategy_id,
                    )

            if self._dispatcher_running:
                try:
                    await self._dispatcher.stop()

                finally:
                    self._dispatcher_running = False

            self._running = False

        logger.info("Strategy manager stopped.")

    # ==================================================================
    # CREATE
    # ==================================================================

    async def create(
        self,
        config: StrategyConfig,
        *,
        market_data: Any | None = None,
        positions: Any | None = None,
        state: Any | None = None,
        clock: Any | None = None,
        auto_start: bool = False,
    ) -> StrategyInstance:
        """
        Create and register one strategy instance.

        ``config.symbols`` represents the complete symbol universe for
        this instance.

        The manager therefore creates:

            ONE StrategyInstance
                ├── symbol A
                ├── symbol B
                └── symbol C

        and never:

            StrategyInstance(symbol A)
            StrategyInstance(symbol B)
            StrategyInstance(symbol C)

        LIVE/PAPER strategies use the normal strategy signal publisher.

        BACKTEST strategies use the isolated backtest publisher and do
        not publish simulated signals onto the live EventBus.

        Args:
            config:
                Runtime strategy configuration.

            market_data:
                Optional market-data context.

            positions:
                Optional position context.

            state:
                Optional strategy state store.

            clock:
                Optional strategy clock.

            auto_start:
                If True, initialize and start the strategy immediately.

                Activation is still determined independently by
                ``config.enabled``.
        """

        async with self._lock:
            existing = self._dispatcher.get_instance(
                config.strategy_id,
            )

            if existing is not None:
                raise StrategyStateError(
                    f"Strategy instance '{config.strategy_id}' " "already exists."
                )

            self._validate_account_assignment(config)

            uses_account_router = self._uses_account_router(
                config.mode,
            )

            if uses_account_router and config.account_id is not None:
                self._account_router.register(
                    strategy_id=config.strategy_id,
                    account_id=config.account_id,
                )

            signal_publisher = self._publisher_for_mode(
                config.mode,
            )

            instance: StrategyInstance | None = None
            instance_registered = False

            try:
                instance = StrategyInstance.create(
                    config,
                    market_data=market_data,
                    positions=positions,
                    state=state,
                    clock=clock,
                    signal_publisher=signal_publisher,
                )

                await self._dispatcher.add_instance(
                    instance,
                )

                instance_registered = True

                try:
                    await instance.initialize()

                    if auto_start:
                        await instance.start()

                except Exception:
                    await self._dispatcher.remove_instance(
                        instance.strategy_id,
                    )

                    instance_registered = False
                    raise

                # ------------------------------------------------------
                # A persisted LIVE/PAPER strategy may be deployed after
                # the manager itself has already started.
                #
                # Therefore the dispatcher must become active before
                # the newly-created strategy is exposed to live market
                # events.
                # ------------------------------------------------------
                if self._running and uses_account_router:
                    await self._start_dispatcher()

            except Exception:
                if instance_registered and instance is not None:
                    try:
                        await self._dispatcher.remove_instance(
                            instance.strategy_id,
                        )

                    except Exception:
                        logger.exception(
                            "Failed to remove partially-created "
                            "strategy instance. id=%s",
                            instance.strategy_id,
                        )

                if uses_account_router:
                    self._account_router.unregister(
                        config.strategy_id,
                    )

                raise

        # ``instance`` is guaranteed to be assigned after successful
        # StrategyInstance.create().
        assert instance is not None

        logger.info(
            "Strategy instance created: "
            "id=%s name=%s mode=%s enabled=%s "
            "active=%s account_id=%s symbols=%s timeframes=%s",
            instance.strategy_id,
            instance.strategy_name,
            instance.mode.value,
            instance.is_enabled,
            instance.is_active,
            instance.config.account_id,
            instance.symbols,
            instance.timeframes,
        )

        return instance

    # ==================================================================
    # ACTIVATION
    # ==================================================================

    async def activate(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """
        Activate a strategy instance.

        Activation does not change lifecycle status.

        Examples:

            READY + activate()
                -> READY + enabled

            RUNNING + activate()
                -> RUNNING + enabled

        The strategy must subsequently be started if its lifecycle is
        still READY.
        """

        instance = self._require_instance(strategy_id)

        instance.activate()

        logger.info(
            "Strategy instance activated: id=%s status=%s",
            strategy_id,
            instance.status.value,
        )

        return instance

    async def deactivate(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """
        Deactivate a strategy instance.

        Deactivation does not stop or destroy the strategy.

        A RUNNING strategy can therefore remain RUNNING while becoming
        inactive and ignoring incoming market data.
        """

        instance = self._require_instance(strategy_id)

        instance.deactivate()

        logger.info(
            "Strategy instance deactivated: id=%s status=%s",
            strategy_id,
            instance.status.value,
        )

        return instance

    # ==================================================================
    # INSTANCE LIFECYCLE
    # ==================================================================

    async def start_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """
        Start a specific strategy instance.

        Starting the lifecycle does not itself activate the strategy.
        Activation remains controlled separately.
        """

        instance = self._require_instance(strategy_id)

        await instance.start()

        logger.info(
            "Strategy instance started: id=%s enabled=%s active=%s",
            strategy_id,
            instance.is_enabled,
            instance.is_active,
        )

        return instance

    async def pause_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Pause a specific strategy instance."""

        instance = self._require_instance(strategy_id)

        await instance.pause()

        logger.info(
            "Strategy instance paused: id=%s",
            strategy_id,
        )

        return instance

    async def resume_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Resume a specific strategy instance."""

        instance = self._require_instance(strategy_id)

        await instance.resume()

        logger.info(
            "Strategy instance resumed: id=%s enabled=%s active=%s",
            strategy_id,
            instance.is_enabled,
            instance.is_active,
        )

        return instance

    async def stop_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Stop a specific strategy instance."""

        instance = self._require_instance(strategy_id)

        await instance.stop()

        logger.info(
            "Strategy instance stopped: id=%s",
            strategy_id,
        )

        return instance

    # ==================================================================
    # REMOVE / RESTART
    # ==================================================================

    async def remove(
        self,
        strategy_id: str,
        *,
        stop: bool = True,
    ) -> StrategyInstance | None:
        """
        Remove a strategy instance.

        Args:
            strategy_id:
                Unique strategy instance identifier.

            stop:
                Stop the strategy before removal.

        Returns:
            Removed strategy instance, or None if it did not exist.
        """

        async with self._lock:
            instance = self._dispatcher.get_instance(
                strategy_id,
            )

            if instance is None:
                return None

            if stop and instance.status not in {
                StrategyStatus.STOPPED,
                StrategyStatus.CREATED,
            }:
                await instance.stop()

            removed = await self._dispatcher.remove_instance(
                strategy_id,
            )

            if removed is not None:
                if self._uses_account_router(removed.mode):
                    self._account_router.unregister(
                        strategy_id,
                    )

        if removed is not None:
            logger.info(
                "Strategy instance removed: id=%s",
                strategy_id,
            )

        return removed

    async def restart(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """
        Restart a strategy instance.

        The existing configuration and runtime dependencies are reused.

        A fresh strategy instance is created, which means strategy state
        owned directly by the implementation is also recreated unless
        the supplied state store persists it.
        """

        instance = self._require_instance(
            strategy_id,
        )

        config = instance.config
        context = instance.context

        await self.remove(
            strategy_id,
            stop=True,
        )

        return await self.create(
            config,
            market_data=context.market_data,
            positions=context.positions,
            state=context.state,
            clock=context.clock,
            auto_start=True,
        )

    async def clear(
        self,
        *,
        stop: bool = True,
    ) -> None:
        """
        Remove all strategy instances.

        Running instances are stopped gracefully by default.

        The dispatcher remains running when the manager itself remains
        running. This allows strategies to be dynamically deployed after
        the clear operation.
        """

        instances = self._dispatcher.instances()

        for instance in instances:
            if stop and instance.status not in {
                StrategyStatus.STOPPED,
                StrategyStatus.CREATED,
            }:
                try:
                    await instance.stop()

                except Exception:
                    logger.exception(
                        "Failed to stop strategy instance " "during clear: id=%s",
                        instance.strategy_id,
                    )

        await self._dispatcher.clear()

        self._account_router.clear()

        logger.info("All strategy instances cleared.")

    # ==================================================================
    # INSTANCE LOOKUP
    # ==================================================================

    def get(
        self,
        strategy_id: str,
    ) -> StrategyInstance | None:
        """Return a strategy instance by ID."""

        return self._dispatcher.get_instance(
            strategy_id,
        )

    def contains(
        self,
        strategy_id: str,
    ) -> bool:
        """Return whether a strategy instance exists."""

        return (
            self._dispatcher.get_instance(
                strategy_id,
            )
            is not None
        )

    def instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return all managed strategy instances."""

        return self._dispatcher.instances()

    def active_instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """
        Return currently active strategy instances.

        Active means:

            enabled=True
            AND
            lifecycle is READY or RUNNING
        """

        return tuple(
            instance for instance in self._dispatcher.instances() if instance.is_active
        )

    def enabled_instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return administratively enabled strategy instances."""

        return tuple(
            instance for instance in self._dispatcher.instances() if instance.is_enabled
        )

    def disabled_instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return administratively disabled strategy instances."""

        return tuple(
            instance
            for instance in self._dispatcher.instances()
            if not instance.is_enabled
        )

    def running_instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return strategy instances whose lifecycle is RUNNING."""

        return tuple(
            instance for instance in self._dispatcher.instances() if instance.is_running
        )

    def instances_by_mode(
        self,
        mode: StrategyMode,
    ) -> tuple[StrategyInstance, ...]:
        """Return instances operating in a specific mode."""

        return tuple(
            instance
            for instance in self._dispatcher.instances()
            if instance.mode is mode
        )

    def instances_by_status(
        self,
        status: StrategyStatus,
    ) -> tuple[StrategyInstance, ...]:
        """Return instances with a specific lifecycle status."""

        return tuple(
            instance
            for instance in self._dispatcher.instances()
            if instance.status is status
        )

    # ==================================================================
    # SNAPSHOTS / MANAGEMENT
    # ==================================================================

    def snapshots(self) -> list[dict[str, Any]]:
        """Return lightweight snapshots of all strategy instances."""

        return [instance.snapshot() for instance in self._dispatcher.instances()]

    def routing_snapshot(self) -> dict[str, object]:
        """Return strategy-account routing information."""

        return self._account_router.snapshot()

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================

    async def _start_dispatcher(self) -> None:
        """
        Start the market-event dispatcher when necessary.

        Dispatcher startup is idempotent at the manager layer, so repeated
        strategy deployments do not repeatedly invoke the dispatcher.
        """

        if self._dispatcher_running:
            return

        try:
            await self._dispatcher.start()

        except Exception:
            self._dispatcher_running = False
            raise

        self._dispatcher_running = True

        logger.info(
            "Strategy dispatcher started.",
        )

    def _require_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Return an instance or raise a clear state error."""

        instance = self._dispatcher.get_instance(
            strategy_id,
        )

        if instance is None:
            raise StrategyStateError(
                f"Strategy instance '{strategy_id}' does not exist."
            )

        return instance

    def _publisher_for_mode(
        self,
        mode: StrategyMode,
    ) -> SignalPublisher:
        """
        Resolve signal delivery for a strategy mode.

        BACKTEST is isolated from the live EventBus.

        LIVE/PAPER use the normal runtime publisher.
        """

        if mode is StrategyMode.BACKTEST:
            return self._backtest_signal_publisher

        return self._signal_publisher

    @staticmethod
    def _uses_account_router(
        mode: StrategyMode,
    ) -> bool:
        """Return whether a strategy mode uses account routing."""

        return mode in {
            StrategyMode.LIVE,
            StrategyMode.PAPER,
        }

    @staticmethod
    def _validate_account_assignment(
        config: StrategyConfig,
    ) -> None:
        """
        Validate account assignment before creating the strategy.

        LIVE/PAPER strategies require an account because their signals
        ultimately enter the broker/execution pipeline.

        BACKTEST strategies do not require StrategyAccountRouter
        registration.
        """

        mode = config.mode.value.upper()

        if mode in {"LIVE", "PAPER"} and config.account_id is None:
            raise StrategyStateError(
                f"Strategy instance '{config.strategy_id}' running in "
                f"{mode} mode cannot be created without an account_id."
            )


__all__ = [
    "StrategyManager",
]
