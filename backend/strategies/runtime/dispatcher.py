"""Market-data dispatcher for the AQE Strategy Engine."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Iterable

from app.events import EventBus, event_bus
from app.events.market import MarketCandleEvent, MarketTickEvent
from app.events.strategy import StrategySignalEvent

from ..core import StrategyStatus
from .instance import StrategyInstance

logger = logging.getLogger(__name__)


class StrategyDispatcher:
    """
    Route AQE market-data events to relevant strategy instances.

    The dispatcher subscribes to the existing AQE EventBus.

    It does not:
        - consume Redis
        - communicate with MT5
        - communicate with brokers
        - access PostgreSQL
        - perform risk checks
        - execute orders

    Routing indexes:

        symbol
            -> tick-capable strategy instance IDs

        (symbol, timeframe)
            -> candle-capable strategy instance IDs
    """

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
    ) -> None:
        """Initialize the strategy dispatcher."""

        self._event_bus = bus or event_bus

        self._instances: dict[str, StrategyInstance] = {}

        self._tick_routes: dict[str, set[str]] = defaultdict(set)

        self._candle_routes: dict[
            tuple[str, str],
            set[str],
        ] = defaultdict(set)

        self._lock = asyncio.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        """Return whether dispatcher is subscribed to EventBus."""

        return self._running

    @property
    def instance_count(self) -> int:
        """Return the number of registered strategy instances."""

        return len(self._instances)

    async def start(self) -> None:
        """
        Start dispatching market-data events.

        Safe to call repeatedly.
        """

        if self._running:
            return

        await self._event_bus.subscribe(
            MarketTickEvent,
            self._handle_tick_event,
        )

        await self._event_bus.subscribe(
            MarketCandleEvent,
            self._handle_candle_event,
        )

        self._running = True

        logger.info("Strategy dispatcher started.")

    async def stop(self) -> None:
        """
        Stop dispatching market-data events.

        Safe to call repeatedly.
        """

        if not self._running:
            return

        await self._event_bus.unsubscribe(
            MarketTickEvent,
            self._handle_tick_event,
        )

        await self._event_bus.unsubscribe(
            MarketCandleEvent,
            self._handle_candle_event,
        )

        self._running = False

        logger.info("Strategy dispatcher stopped.")

    async def add_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """
        Register a strategy instance with the dispatcher.

        Strategy IDs must be unique.
        """

        async with self._lock:
            if instance.strategy_id in self._instances:
                raise ValueError(
                    f"Strategy instance "
                    f"'{instance.strategy_id}' is already registered."
                )

            self._instances[instance.strategy_id] = instance

            self._build_routes_for_instance(
                instance,
            )

        logger.info(
            "Strategy instance registered with dispatcher: "
            "id=%s name=%s symbols=%s timeframes=%s",
            instance.strategy_id,
            instance.strategy_name,
            instance.symbols,
            instance.timeframes,
        )

    async def remove_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance | None:
        """
        Remove a strategy instance and its routing entries.

        The instance itself is not stopped by this method.
        Lifecycle ownership remains with StrategyManager.
        """

        async with self._lock:
            instance = self._instances.pop(
                strategy_id,
                None,
            )

            if instance is None:
                return None

            self._remove_routes_for_instance(
                instance,
            )

        logger.info(
            "Strategy instance removed from dispatcher: id=%s",
            strategy_id,
        )

        return instance

    async def replace_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """
        Replace an existing instance with another instance.

        The replacement must use the same strategy ID if an existing
        instance is being replaced.
        """

        async with self._lock:
            existing = self._instances.get(
                instance.strategy_id,
            )

            if existing is not None:
                self._remove_routes_for_instance(
                    existing,
                )

            self._instances[instance.strategy_id] = instance

            self._build_routes_for_instance(
                instance,
            )

        logger.info(
            "Strategy instance replaced: id=%s",
            instance.strategy_id,
        )

    async def clear(self) -> None:
        """
        Remove all strategy instances and routing indexes.

        Instances are not stopped by this method.
        """

        async with self._lock:
            self._instances.clear()
            self._tick_routes.clear()
            self._candle_routes.clear()

        logger.info("Strategy dispatcher instances cleared.")

    def get_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance | None:
        """Return a registered strategy instance."""

        return self._instances.get(
            strategy_id,
        )

    def instances(
        self,
    ) -> tuple[StrategyInstance, ...]:
        """Return all registered strategy instances."""

        return tuple(
            self._instances.values(),
        )

    def route_for_tick(
        self,
        symbol: str,
    ) -> tuple[StrategyInstance, ...]:
        """
        Return strategy instances interested in ticks for a symbol.
        """

        normalized_symbol = symbol.strip()

        strategy_ids = self._tick_routes.get(
            normalized_symbol,
            set(),
        )

        return tuple(
            self._instances[strategy_id]
            for strategy_id in strategy_ids
            if strategy_id in self._instances
        )

    def route_for_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> tuple[StrategyInstance, ...]:
        """
        Return strategy instances interested in a symbol/timeframe.
        """

        route_key = (
            symbol.strip(),
            timeframe.strip().upper(),
        )

        strategy_ids = self._candle_routes.get(
            route_key,
            set(),
        )

        return tuple(
            self._instances[strategy_id]
            for strategy_id in strategy_ids
            if strategy_id in self._instances
        )

    async def dispatch_tick(
        self,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a tick directly to matching strategy instances.

        This method is useful for tests, replay, and controlled runtime
        processing. Normal live operation receives events through the
        EventBus subscription established by start().
        """

        instances = self.route_for_tick(
            event.symbol,
        )

        if not instances:
            return ()

        return await self._dispatch_tick(
            event,
            instances,
        )

    async def dispatch_candle(
        self,
        event: MarketCandleEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a candle directly to matching strategy instances.

        This method is useful for tests, replay, and controlled runtime
        processing. Normal live operation receives events through the
        EventBus subscription established by start().
        """

        instances = self.route_for_candle(
            event.symbol,
            event.timeframe,
        )

        if not instances:
            return ()

        return await self._dispatch_candle(
            event,
            instances,
        )

    async def _handle_tick_event(
        self,
        event: MarketTickEvent,
    ) -> None:
        """Handle a tick received from the AQE EventBus."""

        await self.dispatch_tick(
            event,
        )

    async def _handle_candle_event(
        self,
        event: MarketCandleEvent,
    ) -> None:
        """Handle a candle received from the AQE EventBus."""

        await self.dispatch_candle(
            event,
        )

    async def _dispatch_tick(
        self,
        event: MarketTickEvent,
        instances: Iterable[StrategyInstance],
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a tick to matching strategy instances concurrently.

        A failure in one strategy is isolated and does not prevent
        other matching strategies from processing the same event.
        """

        tasks = [
            asyncio.create_task(
                self._safe_handle_tick(
                    instance,
                    event,
                )
            )
            for instance in instances
            if instance.is_active and instance.status is not StrategyStatus.ERROR
        ]

        if not tasks:
            return ()

        results = await asyncio.gather(
            *tasks,
        )

        return self._flatten_results(
            results,
        )

    async def _dispatch_candle(
        self,
        event: MarketCandleEvent,
        instances: Iterable[StrategyInstance],
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a candle to matching strategy instances concurrently.

        A failure in one strategy is isolated and does not prevent
        other matching strategies from processing the same event.
        """

        tasks = [
            asyncio.create_task(
                self._safe_handle_candle(
                    instance,
                    event,
                )
            )
            for instance in instances
            if instance.is_active and instance.status is not StrategyStatus.ERROR
        ]

        if not tasks:
            return ()

        results = await asyncio.gather(
            *tasks,
        )

        return self._flatten_results(
            results,
        )

    async def _safe_handle_tick(
        self,
        instance: StrategyInstance,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a tick while isolating strategy failures.
        """

        try:
            return await instance.handle_tick(
                event,
            )

        except Exception:
            logger.exception(
                "Strategy instance failed while processing tick: "
                "strategy_id=%s symbol=%s",
                instance.strategy_id,
                event.symbol,
            )

            return ()

    async def _safe_handle_candle(
        self,
        instance: StrategyInstance,
        event: MarketCandleEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a candle while isolating strategy failures.
        """

        try:
            return await instance.handle_candle(
                event,
            )

        except Exception:
            logger.exception(
                "Strategy instance failed while processing candle: "
                "strategy_id=%s symbol=%s timeframe=%s",
                instance.strategy_id,
                event.symbol,
                event.timeframe,
            )

            return ()

    @staticmethod
    def _flatten_results(
        results: Iterable[tuple[StrategySignalEvent, ...]],
    ) -> tuple[StrategySignalEvent, ...]:
        """Flatten per-strategy signal-event results."""

        flattened: list[StrategySignalEvent] = []

        for result in results:
            flattened.extend(result)

        return tuple(flattened)

    def _build_routes_for_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """Add routing entries for a strategy instance."""

        for symbol in instance.symbols:
            normalized_symbol = symbol.strip()

            if "TICK" in instance.timeframes:
                self._tick_routes[normalized_symbol].add(
                    instance.strategy_id,
                )

            for timeframe in instance.timeframes:
                normalized_timeframe = timeframe.strip().upper()

                if normalized_timeframe == "TICK":
                    continue

                self._candle_routes[
                    (
                        normalized_symbol,
                        normalized_timeframe,
                    )
                ].add(
                    instance.strategy_id,
                )

    def _remove_routes_for_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """Remove routing entries for a strategy instance."""

        for symbol in instance.symbols:
            normalized_symbol = symbol.strip()

            tick_route = self._tick_routes.get(
                normalized_symbol,
            )

            if tick_route is not None:
                tick_route.discard(
                    instance.strategy_id,
                )

                if not tick_route:
                    self._tick_routes.pop(
                        normalized_symbol,
                        None,
                    )

            for timeframe in instance.timeframes:
                normalized_timeframe = timeframe.strip().upper()

                if normalized_timeframe == "TICK":
                    continue

                route_key = (
                    normalized_symbol,
                    normalized_timeframe,
                )

                candle_route = self._candle_routes.get(
                    route_key,
                )

                if candle_route is None:
                    continue

                candle_route.discard(
                    instance.strategy_id,
                )

                if not candle_route:
                    self._candle_routes.pop(
                        route_key,
                        None,
                    )

    def routing_snapshot(self) -> dict[str, object]:
        """
        Return routing information for diagnostics and monitoring.

        Only strategy IDs are exposed; strategy runtime objects are
        never included.
        """

        return {
            "running": self._running,
            "instance_count": len(self._instances),
            "tick_routes": {
                symbol: sorted(strategy_ids)
                for symbol, strategy_ids in self._tick_routes.items()
            },
            "candle_routes": {
                f"{symbol}:{timeframe}": sorted(strategy_ids)
                for (symbol, timeframe), strategy_ids in self._candle_routes.items()
            },
        }
