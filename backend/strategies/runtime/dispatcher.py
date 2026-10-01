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
    Route AQE market-data events to configured strategy instances.

    The dispatcher is responsible for:

        Market Event
             │
             ▼
        Route lookup
             │
             ├── Strategy A
             ├── Strategy B
             └── Strategy C
                    │
                    ▼
             StrategyInstance
                    │
                    ▼
             TradingSignal
                    │
                    ▼
             StrategySignalEvent

    The dispatcher does NOT:

        - consume Redis
        - communicate with MT5
        - communicate with brokers
        - access PostgreSQL
        - perform risk checks
        - calculate position sizing
        - execute orders
        - decide whether a TradingSignal should trade

    Strategy instances are owned by StrategyManager.

    The dispatcher only maintains routing indexes and delivers events.

    Multi-symbol behavior:

        One StrategyInstance may contain:

            (
                "XAUUSD.s",
                "AUDCAD.s",
                "BTCUSD",
            )

        The dispatcher therefore creates routing entries for all three
        symbols while still maintaining only one StrategyInstance.
    """

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
    ) -> None:
        """Initialize the strategy dispatcher."""

        self._event_bus = bus if bus is not None else event_bus

        self._instances: dict[str, StrategyInstance] = {}

        # symbol -> strategy IDs capable of receiving ticks
        self._tick_routes: dict[str, set[str]] = defaultdict(set)

        # (symbol, timeframe) -> strategy IDs capable of receiving candles
        self._candle_routes: dict[
            tuple[str, str],
            set[str],
        ] = defaultdict(set)

        self._lock = asyncio.Lock()
        self._running = False

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def running(self) -> bool:
        """Return whether the dispatcher is subscribed to EventBus."""

        return self._running

    @property
    def instance_count(self) -> int:
        """Return the number of registered strategy instances."""

        return len(self._instances)

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(self) -> None:
        """
        Start dispatching market-data events.

        The dispatcher subscribes to the AQE EventBus for:

            - MarketTickEvent
            - MarketCandleEvent

        Safe to call repeatedly.
        """

        async with self._lock:
            if self._running:
                return

            await self._event_bus.subscribe(
                MarketTickEvent,
                self._handle_tick_event,
            )

            try:
                await self._event_bus.subscribe(
                    MarketCandleEvent,
                    self._handle_candle_event,
                )

            except Exception:
                # If the second subscription fails, remove the first
                # subscription so the dispatcher does not remain
                # partially started.
                try:
                    await self._event_bus.unsubscribe(
                        MarketTickEvent,
                        self._handle_tick_event,
                    )
                except Exception:
                    logger.exception(
                        "Failed to roll back MarketTickEvent "
                        "subscription after dispatcher startup failure."
                    )

                raise

            self._running = True

        logger.info("Strategy dispatcher started.")

    async def stop(self) -> None:
        """
        Stop dispatching market-data events.

        Safe to call repeatedly.
        """

        async with self._lock:
            if not self._running:
                return

            try:
                await self._event_bus.unsubscribe(
                    MarketTickEvent,
                    self._handle_tick_event,
                )

            finally:
                try:
                    await self._event_bus.unsubscribe(
                        MarketCandleEvent,
                        self._handle_candle_event,
                    )
                finally:
                    self._running = False

        logger.info("Strategy dispatcher stopped.")

    # ==================================================================
    # INSTANCE MANAGEMENT
    # ==================================================================

    async def add_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """
        Register a strategy instance with the dispatcher.

        The instance's complete symbol/timeframe universe is indexed.

        Strategy IDs must be unique.

        This method does not initialize, start, activate, or stop the
        strategy.
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
        Remove a strategy instance and all routing entries.

        The strategy lifecycle is not changed.

        StrategyManager owns lifecycle operations such as stop().
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
        Replace an existing strategy instance.

        If an instance with the same strategy ID exists, its routing
        entries are removed before the replacement is registered.

        The replacement itself is not started or initialized here.
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

        Strategy lifecycles are not changed.

        StrategyManager is responsible for stopping instances before
        calling clear() when graceful shutdown is required.
        """

        async with self._lock:
            self._instances.clear()
            self._tick_routes.clear()
            self._candle_routes.clear()

        logger.info("Strategy dispatcher instances cleared.")

    # ==================================================================
    # INSTANCE LOOKUP
    # ==================================================================

    def get_instance(
        self,
        strategy_id: str,
    ) -> StrategyInstance | None:
        """Return a registered strategy instance by ID."""

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

    # ==================================================================
    # ROUTING LOOKUP
    # ==================================================================

    def route_for_tick(
        self,
        symbol: str,
    ) -> tuple[StrategyInstance, ...]:
        """
        Return strategy instances interested in ticks for a symbol.

        Only instances that are currently capable of processing the
        symbol are returned.
        """

        normalized_symbol = self._normalize_symbol(
            symbol,
        )

        strategy_ids = self._tick_routes.get(
            normalized_symbol,
            set(),
        )

        instances: list[StrategyInstance] = []

        for strategy_id in strategy_ids:
            instance = self._instances.get(
                strategy_id,
            )

            if instance is None:
                continue

            if not instance.supports_tick(
                normalized_symbol,
            ):
                continue

            instances.append(
                instance,
            )

        return tuple(instances)

    def route_for_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> tuple[StrategyInstance, ...]:
        """
        Return strategy instances interested in a symbol/timeframe.

        Timeframe matching is case-insensitive.
        Symbol matching preserves the symbol's actual case.
        """

        normalized_symbol = self._normalize_symbol(
            symbol,
        )

        normalized_timeframe = self._normalize_timeframe(
            timeframe,
        )

        route_key = (
            normalized_symbol,
            normalized_timeframe,
        )

        strategy_ids = self._candle_routes.get(
            route_key,
            set(),
        )

        instances: list[StrategyInstance] = []

        for strategy_id in strategy_ids:
            instance = self._instances.get(
                strategy_id,
            )

            if instance is None:
                continue

            if not instance.supports_candle(
                normalized_symbol,
                normalized_timeframe,
            ):
                continue

            instances.append(
                instance,
            )

        return tuple(instances)

    # ==================================================================
    # DIRECT DISPATCH
    # ==================================================================

    async def dispatch_tick(
        self,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a tick directly to matching strategy instances.

        This method is useful for:

            - tests
            - replay
            - backtesting
            - controlled event processing

        Live operation normally receives events through EventBus after
        start() has been called.
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

        This method is useful for:

            - tests
            - replay
            - backtesting
            - controlled event processing

        Live operation normally receives events through EventBus after
        start() has been called.
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

    # ==================================================================
    # EVENT BUS HANDLERS
    # ==================================================================

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

    # ==================================================================
    # CONCURRENT DISPATCH
    # ==================================================================

    async def _dispatch_tick(
        self,
        event: MarketTickEvent,
        instances: Iterable[StrategyInstance],
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Dispatch a tick concurrently to matching strategy instances.

        A failure in one strategy is isolated from other strategies
        receiving the same market event.
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
        Dispatch a candle concurrently to matching strategy instances.

        A failure in one strategy is isolated from other strategies
        receiving the same market event.
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

    # ==================================================================
    # ERROR ISOLATION
    # ==================================================================

    async def _safe_handle_tick(
        self,
        instance: StrategyInstance,
        event: MarketTickEvent,
    ) -> tuple[StrategySignalEvent, ...]:
        """
        Process a tick while isolating strategy failures.

        A strategy exception must not terminate the dispatcher or
        prevent unrelated strategies from receiving the same event.
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

    # ==================================================================
    # RESULT HANDLING
    # ==================================================================

    @staticmethod
    def _flatten_results(
        results: Iterable[tuple[StrategySignalEvent, ...]],
    ) -> tuple[StrategySignalEvent, ...]:
        """Flatten per-strategy signal-event results."""

        flattened: list[StrategySignalEvent] = []

        for result in results:
            flattened.extend(
                result,
            )

        return tuple(flattened)

    # ==================================================================
    # ROUTE INDEX MANAGEMENT
    # ==================================================================

    def _build_routes_for_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """
        Build routing indexes for one strategy instance.

        One instance may generate many routing entries because it can
        monitor many symbols and timeframes.
        """

        strategy_id = instance.strategy_id

        for symbol in instance.symbols:
            normalized_symbol = self._normalize_symbol(
                symbol,
            )

            for timeframe in instance.timeframes:
                normalized_timeframe = self._normalize_timeframe(
                    timeframe,
                )

                if normalized_timeframe == "TICK":
                    self._tick_routes[normalized_symbol].add(
                        strategy_id,
                    )

                    continue

                self._candle_routes[
                    (
                        normalized_symbol,
                        normalized_timeframe,
                    )
                ].add(
                    strategy_id,
                )

    def _remove_routes_for_instance(
        self,
        instance: StrategyInstance,
    ) -> None:
        """Remove all routing entries belonging to an instance."""

        strategy_id = instance.strategy_id

        for symbol in instance.symbols:
            normalized_symbol = self._normalize_symbol(
                symbol,
            )

            tick_route = self._tick_routes.get(
                normalized_symbol,
            )

            if tick_route is not None:
                tick_route.discard(
                    strategy_id,
                )

                if not tick_route:
                    self._tick_routes.pop(
                        normalized_symbol,
                        None,
                    )

            for timeframe in instance.timeframes:
                normalized_timeframe = self._normalize_timeframe(
                    timeframe,
                )

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
                    strategy_id,
                )

                if not candle_route:
                    self._candle_routes.pop(
                        route_key,
                        None,
                    )

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        """
        Normalize a broker symbol for routing.

        Symbol case is intentionally preserved because broker symbols
        such as XAUUSD.s can be case-sensitive at integration
        boundaries.
        """

        if not isinstance(symbol, str):
            raise TypeError("Strategy routing symbol must be a string.")

        normalized = symbol.strip()

        if not normalized:
            raise ValueError("Strategy routing symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_timeframe(
        timeframe: str,
    ) -> str:
        """Normalize a strategy timeframe for routing."""

        if not isinstance(timeframe, str):
            raise TypeError("Strategy routing timeframe must be a string.")

        normalized = timeframe.strip().upper()

        if not normalized:
            raise ValueError("Strategy routing timeframe cannot be empty.")

        return normalized

    # ==================================================================
    # DIAGNOSTICS
    # ==================================================================

    def routing_snapshot(self) -> dict[str, object]:
        """
        Return routing information for diagnostics and monitoring.

        Runtime strategy objects are never exposed.
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
                for (
                    symbol,
                    timeframe,
                ), strategy_ids in self._candle_routes.items()
            },
        }

    def __repr__(self) -> str:
        """Return a useful representation for logs/debugging."""

        return (
            "StrategyDispatcher("
            f"running={self._running!r}, "
            f"instance_count={len(self._instances)!r}"
            ")"
        )
