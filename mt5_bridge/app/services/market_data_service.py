
from __future__ import annotations

import asyncio
import inspect
import math
from datetime import datetime, timezone
from threading import RLock
from typing import Awaitable, Callable

from app.core.logging import logger
from app.infrastructure.redis import redis_publisher
from app.schemas.market_data import MarketTick
from app.services.connection_service import connection_service
from app.broker.market_data import MarketDataBroker


TickHandler = Callable[
    [MarketTick],
    Awaitable[None] | None,
]


class MarketDataService:
    """
    Continuously collect and publish normalized MT5 market data.

    MT5 authentication and reconnection belong to ConnectionService.
    MT5 API operations are serialized by the shared lock used by
    MarketDataBroker and MT5Client.

    Market data has two publication paths:
        1. Local in-process handlers.
        2. Redis Streams for distributed AQE components.

    Redis stream:
        aqe:market-data

    The service can start before MT5 is connected. Existing
    subscriptions remain active during outages and polling resumes
    when ConnectionService confirms the intended account is healthy.
    """

    REDIS_STREAM = "aqe:market-data"
    REDIS_EVENT_TYPE = "MarketTickEvent"

    def __init__(
        self,
        broker: MarketDataBroker | None = None,
        poll_interval: float = 0.1,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero.")

        self.broker = broker or MarketDataBroker()
        self.poll_interval = poll_interval

        self._running = False
        self._task: asyncio.Task | None = None

        # API routes may run in worker threads while the polling
        # coroutine runs on the event loop.
        self._state_lock = RLock()

        self._symbols: set[str] = set()
        self._handlers: list[TickHandler] = []
        self._last_ticks: dict[str, MarketTick] = {}

        self._last_publish_error: str | None = None
        self._last_publish_error_at: datetime | None = None
        self._last_publish_success_at: datetime | None = None

    # =========================================================
    # SUBSCRIPTIONS
    # =========================================================

    def subscribe(self, symbol: str) -> None:
        """Add a canonical broker symbol to the subscription set."""

        symbol = symbol.strip()

        if not symbol:
            raise ValueError("Symbol cannot be empty.")

        with self._state_lock:
            if symbol in self._symbols:
                logger.debug(
                    "Symbol already subscribed: %s",
                    symbol,
                )
                return

            self._symbols.add(symbol)

        logger.info(
            "Market-data subscription added: %s",
            symbol,
        )

    def unsubscribe(self, symbol: str) -> None:
        """Remove a symbol from live market-data collection."""

        symbol = symbol.strip()

        with self._state_lock:
            self._symbols.discard(symbol)
            self._last_ticks.pop(symbol, None)

        logger.info(
            "Market-data subscription removed: %s",
            symbol,
        )

    def subscriptions(self) -> list[str]:
        """Return subscribed symbols in deterministic order."""

        with self._state_lock:
            return sorted(self._symbols)

    # =========================================================
    # LOCAL EVENT HANDLERS
    # =========================================================

    def add_handler(self, handler: TickHandler) -> None:
        """Register an in-process market-data handler."""

        with self._state_lock:
            if handler in self._handlers:
                return

            self._handlers.append(handler)

        logger.debug(
            "Market-data handler registered: %s",
            getattr(handler, "__name__", repr(handler)),
        )

    def remove_handler(self, handler: TickHandler) -> None:
        """Remove a previously registered handler."""

        with self._state_lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    # =========================================================
    # CONNECTION HEALTH
    # =========================================================

    @staticmethod
    def _mt5_ready() -> bool:
        """
        Check the connection layer's verified MT5 account status.

        Do not call mt5.terminal_info() or mt5.account_info() directly
        here. ConnectionService owns the account identity check and
        coordinates its MT5Client operations with the shared MT5 lock.

        This check deliberately does not trigger a second reconnect
        loop. ConnectionService's background monitor owns recovery.
        """

        try:
            return connection_service.is_connected()

        except Exception:
            logger.exception(
                "Unable to check MT5 connection health."
            )
            return False

    # =========================================================
    # NORMALIZED TICK VALIDATION
    # =========================================================

    @staticmethod
    def _validate_normalized_tick(
        tick: MarketTick,
    ) -> bool:
        """
        Reject invalid normalized market data before publication.
        """

        errors = tick.validation_errors()

        if errors:
            logger.warning(
                "Rejected invalid normalized market tick: "
                "symbol=%s errors=%s payload=%s",
                tick.symbol,
                errors,
                tick.model_dump(mode="json"),
            )
            return False

        values = (
            tick.bid,
            tick.ask,
            tick.last,
            tick.volume_real,
        )

        if not all(math.isfinite(value) for value in values):
            logger.warning(
                "Rejected non-finite normalized market tick: %s",
                tick.model_dump(mode="json"),
            )
            return False

        return True

    # =========================================================
    # TICK RETRIEVAL
    # =========================================================

    def get_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """
        Retrieve and normalize a tick.

        Connection health is checked before requesting data. The
        broker then acquires the shared MT5 API lock for the actual
        symbol lookup and tick retrieval.

        The service does not hold the MT5 lock while acquiring the
        ConnectionService state lock; this avoids lock-order deadlocks.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve tick: empty symbol."
            )
            return None

        if not self._mt5_ready():
            return None

        # MarketDataBroker.get_tick() owns the shared MT5 API lock
        # for its complete synchronous terminal operation.
        try:
            tick = self.broker.get_tick(symbol)

        except Exception:
            logger.exception(
                "MT5 broker tick retrieval failed for %s",
                symbol,
            )
            return None

        if tick is None:
            return None

        try:
            data = tick._asdict()

        except (AttributeError, TypeError):
            logger.error(
                "MT5 broker returned an invalid tick object for %s",
                symbol,
            )
            return None

        try:
            normalized = MarketTick(
                symbol=symbol,
                timestamp=int(data.get("time", 0)),
                bid=float(data.get("bid", 0.0)),
                ask=float(data.get("ask", 0.0)),
                last=float(data.get("last", 0.0)),
                volume=int(data.get("volume", 0)),
                volume_real=float(data.get("volume_real", 0.0)),
            )

        except (TypeError, ValueError, OverflowError):
            logger.exception(
                "Failed to normalize MT5 tick for %s: raw_tick=%r",
                symbol,
                data,
            )
            return None

        if not self._validate_normalized_tick(normalized):
            return None

        return normalized

    # =========================================================
    # REDIS PUBLICATION
    # =========================================================

    async def _publish_redis(
        self,
        tick: MarketTick,
    ) -> None:
        """
        Publish a validated tick to Redis Streams.

        Redis failures are recorded without terminating market-data
        polling or suppressing local handlers.
        """

        try:
            message_id = await redis_publisher.publish(
                self.REDIS_EVENT_TYPE,
                tick.model_dump(mode="json"),
                stream=self.REDIS_STREAM,
            )

            with self._state_lock:
                self._last_publish_error = None
                self._last_publish_success_at = datetime.now(
                    timezone.utc
                )

            logger.debug(
                "Market tick published to Redis: "
                "stream=%s symbol=%s message_id=%s",
                self.REDIS_STREAM,
                tick.symbol,
                message_id,
            )

        except Exception as exc:
            error_at = datetime.now(timezone.utc)

            with self._state_lock:
                self._last_publish_error = str(exc)
                self._last_publish_error_at = error_at

            logger.exception(
                "Failed to publish market tick to Redis for %s. "
                "Local handlers will continue.",
                tick.symbol,
            )

    async def _publish(
        self,
        tick: MarketTick,
    ) -> None:
        """Publish a validated tick to Redis and local handlers."""

        if not self._validate_normalized_tick(tick):
            return

        await self._publish_redis(tick)

        # Take a snapshot under the lock, then call handlers without
        # holding it. Handlers may register or remove other handlers.
        with self._state_lock:
            handlers = list(self._handlers)

        for handler in handlers:
            try:
                result = handler(tick)

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception(
                    "Market-data handler failed for %s",
                    tick.symbol,
                )

    # =========================================================
    # POLLING LOOP
    # =========================================================

    async def _poll(self) -> None:
        """
        Continuously poll subscriptions and publish valid ticks.

        Transient connection failures do not terminate the loop.
        Reconnection itself is delegated to ConnectionService.
        """

        logger.info(
            "Market-data polling started (interval=%s seconds)",
            self.poll_interval,
        )

        connection_warning_logged = False

        while self._running:
            with self._state_lock:
                symbols = sorted(self._symbols)

            if not symbols:
                await asyncio.sleep(self.poll_interval)
                continue

            # A failed health check is not a reason to stop the service.
            ready = await asyncio.to_thread(self._mt5_ready)

            if not ready:
                if not connection_warning_logged:
                    logger.warning(
                        "MT5 account is not ready. "
                        "Polling is waiting for connection recovery."
                    )
                    connection_warning_logged = True

                await asyncio.sleep(self.poll_interval)
                continue

            if connection_warning_logged:
                logger.info(
                    "MT5 account connection is healthy. "
                    "Market-data polling resumed."
                )
                connection_warning_logged = False

            for symbol in symbols:
                if not self._running:
                    break

                # Ignore symbols removed after this iteration's snapshot.
                with self._state_lock:
                    if symbol not in self._symbols:
                        continue

                try:
                    tick = await asyncio.to_thread(
                        self.get_tick,
                        symbol,
                    )

                    if tick is None:
                        continue

                    with self._state_lock:
                        previous = self._last_ticks.get(symbol)

                        if previous == tick:
                            continue

                        self._last_ticks[symbol] = tick

                    await self._publish(tick)

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "Market-data polling failed for %s",
                        symbol,
                    )

            await asyncio.sleep(self.poll_interval)

        logger.info("Market-data polling stopped.")

    # =========================================================
    # LIFECYCLE
    # =========================================================

    def start(self) -> None:
        """Start the background polling task."""

        if self._running:
            logger.warning(
                "Market-data service is already running."
            )
            return

        self._running = True

        self._task = asyncio.create_task(
            self._poll(),
            name="mt5-market-data-poller",
        )

        logger.info("Market-data service started.")

    async def stop(self) -> None:
        """Stop the polling task cleanly."""

        if not self._running and self._task is None:
            return

        self._running = False

        task = self._task
        self._task = None

        if task is not None:
            task.cancel()

            try:
                await task

            except asyncio.CancelledError:
                pass

            except Exception:
                logger.exception(
                    "Market-data polling task failed during shutdown."
                )

        logger.info("Market-data service stopped.")

    # =========================================================
    # STATUS PROPERTIES
    # =========================================================

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_publish_error(self) -> str | None:
        with self._state_lock:
            return self._last_publish_error

    @property
    def last_publish_error_at(self) -> datetime | None:
        with self._state_lock:
            return self._last_publish_error_at

    @property
    def last_publish_success_at(self) -> datetime | None:
        with self._state_lock:
            return self._last_publish_success_at

    def last_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """Return the last collected tick for a symbol."""

        with self._state_lock:
            return self._last_ticks.get(symbol)


market_data_service = MarketDataService(
    poll_interval=0.1,
)
