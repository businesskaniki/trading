"""Strategy instance lifecycle management for the AQE Strategy Engine."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..bootstrap import StrategyBootstrap, strategy_bootstrap
from ..core import StrategyConfig, StrategyMode, StrategyStatus
from ..core.exceptions import StrategyStateError
from .dispatcher import StrategyDispatcher
from .instance import StrategyInstance
from .signal_publisher import StrategySignalPublisher

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    Manage the lifecycle of AQE strategy instances.

    The manager owns strategy instances and coordinates them with the
    StrategyDispatcher and StrategySignalPublisher.

    Responsibilities:
        - bootstrap strategy definitions
        - create strategy instances
        - register instances with the dispatcher
        - initialize strategies
        - start and stop strategies
        - pause and resume strategies
        - remove strategy instances
        - expose runtime state
        - inject shared runtime dependencies

    It does not:
        - consume Redis
        - communicate with MT5
        - communicate with brokers
        - execute orders
        - calculate position sizing
        - persist trading data
    """

    def __init__(
        self,
        dispatcher: StrategyDispatcher | None = None,
        signal_publisher: StrategySignalPublisher | None = None,
        bootstrap: StrategyBootstrap | None = None,
    ) -> None:
        """Initialize the strategy manager."""

        self._dispatcher = dispatcher or StrategyDispatcher()

        self._signal_publisher = signal_publisher or StrategySignalPublisher()

        self._bootstrap = bootstrap or strategy_bootstrap

        self._lock = asyncio.Lock()
        self._running = False

    @property
    def dispatcher(self) -> StrategyDispatcher:
        """Return the strategy dispatcher."""

        return self._dispatcher

    @property
    def signal_publisher(self) -> StrategySignalPublisher:
        """Return the shared strategy signal publisher."""

        return self._signal_publisher

    @property
    def bootstrap(self) -> StrategyBootstrap:
        """Return the strategy bootstrap service."""

        return self._bootstrap

    @property
    def running(self) -> bool:
        """Return whether the strategy manager is running."""

        return self._running

    @property
    def instance_count(self) -> int:
        """Return the number of managed strategy instances."""

        return self._dispatcher.instance_count

    async def start(self) -> None:
        """
        Start the strategy runtime.

        Strategy definitions are bootstrapped before the dispatcher
        starts accepting market-data events.

        Existing instances are not automatically started. Their
        individual lifecycle remains controlled by the manager.
        """

        async with self._lock:
            if self._running:
                return

            await self._bootstrap.start()

            await self._dispatcher.start()

            self._running = True

        logger.info("Strategy manager started.")

    async def stop(self) -> None:
        """
        Stop the strategy runtime.

        All existing strategy instances are stopped before the
        dispatcher unsubscribes from the AQE EventBus.
        """

        async with self._lock:
            if not self._running:
                return

            instances = self._dispatcher.instances()

            for instance in instances:
                try:
                    await instance.stop()

                except Exception:
                    logger.exception(
                        "Failed to stop strategy instance: id=%s",
                        instance.strategy_id,
                    )

            await self._dispatcher.stop()

            self._running = False

        logger.info("Strategy manager stopped.")

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
        Create and register a strategy instance.

        Args:
            config:
                Runtime configuration for the strategy instance.

            market_data:
                Optional read-only market-data view.

            positions:
                Optional read-only position view.

            state:
                Optional strategy state store.

            clock:
                Optional strategy clock.

            auto_start:
                Start the strategy after initialization when enabled.

        Returns:
            The created strategy instance.
        """

        async with self._lock:
            if (
                self._dispatcher.get_instance(
                    config.strategy_id,
                )
                is not None
            ):
                raise StrategyStateError(
                    f"Strategy instance " f"'{config.strategy_id}' already exists."
                )

            instance = StrategyInstance.create(
                config,
                market_data=market_data,
                positions=positions,
                state=state,
                clock=clock,
                signal_publisher=self._signal_publisher,
            )

            await self._dispatcher.add_instance(
                instance,
            )

            try:
                await instance.initialize()

                if auto_start and config.enabled:
                    await instance.start()

            except Exception:
                await self._dispatcher.remove_instance(
                    instance.strategy_id,
                )

                raise

        logger.info(
            "Strategy instance created: "
            "id=%s name=%s mode=%s symbols=%s timeframes=%s",
            instance.strategy_id,
            instance.strategy_name,
            instance.mode.value,
            instance.symbols,
            instance.timeframes,
        )

        return instance

    async def start_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Start a specific strategy instance."""

        instance = self._require_instance(
            strategy_id,
        )

        await instance.start()

        logger.info(
            "Strategy instance started: id=%s",
            strategy_id,
        )

        return instance

    async def pause_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Pause a specific strategy instance."""

        instance = self._require_instance(
            strategy_id,
        )

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

        instance = self._require_instance(
            strategy_id,
        )

        await instance.resume()

        logger.info(
            "Strategy instance resumed: id=%s",
            strategy_id,
        )

        return instance

    async def stop_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance:
        """Stop a specific strategy instance."""

        instance = self._require_instance(
            strategy_id,
        )

        await instance.stop()

        logger.info(
            "Strategy instance stopped: id=%s",
            strategy_id,
        )

        return instance

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
                Stop the strategy before removing it.

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
        Restart a strategy instance while preserving its runtime
        dependencies.
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

        By default, running instances are stopped gracefully first.
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

        logger.info("All strategy instances cleared.")

    def get(
        self,
        strategy_id: str,
    ) -> StrategyInstance | None:
        """Return a strategy instance by ID."""

        return self._dispatcher.get_instance(
            strategy_id,
        )

    def instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return all strategy instances."""

        return self._dispatcher.instances()

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

    def snapshots(
        self,
    ) -> list[dict[str, Any]]:
        """Return lightweight snapshots of all strategy instances."""

        return [instance.snapshot() for instance in self._dispatcher.instances()]

    def routing_snapshot(
        self,
    ) -> dict[str, object]:
        """Return dispatcher routing information."""

        return self._dispatcher.routing_snapshot()

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
