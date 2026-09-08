import asyncio
import inspect
import time
from typing import Awaitable, Callable

from app.broker.market_data import MarketDataBroker
from app.core.logging import logger
from app.infrastructure.redis import (
    redis_client,
    redis_publisher,
)
from app.schemas.market_data import MarketTick

TickHandler = Callable[
    [MarketTick],
    Awaitable[None] | None,
]


class MarketDataService:
    """
    Application service responsible for continuously collecting
    and publishing normalized market data from MetaTrader 5.

    MT5 authentication is handled by the connection layer.
    This service only consumes the already-authenticated MT5 session.

    Market data has two publication paths:

    1. Local in-process handlers.
    2. Redis Streams for distributed AQE components.

    Redis stream:

        aqe:market-data
    """

    REDIS_STREAM = "aqe:market-data"
    REDIS_EVENT_TYPE = "MarketTickEvent"

    def __init__(
        self,
        broker: MarketDataBroker | None = None,
        poll_interval: float = 0.1,
    ):
        self.broker = broker or MarketDataBroker()

        self.poll_interval = poll_interval

        self._running = False
        self._task: asyncio.Task | None = None

        self._symbols: set[str] = set()
        self._handlers: list[TickHandler] = []

        self._last_ticks: dict[str, MarketTick] = {}

    # =========================================================
    # Symbol subscriptions
    # =========================================================

    def subscribe(self, symbol: str) -> None:
        """
        Subscribe to live market data for a symbol.
        """

        symbol = symbol.strip()

        if not symbol:
            raise ValueError("Symbol cannot be empty.")

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
        """
        Remove a symbol from the live market-data stream.
        """

        self._symbols.discard(symbol)

        self._last_ticks.pop(symbol, None)

        logger.info(
            "Market-data subscription removed: %s",
            symbol,
        )

    def subscriptions(self) -> list[str]:
        """
        Return all currently subscribed symbols.
        """

        return sorted(self._symbols)

    # =========================================================
    # Handlers
    # =========================================================

    def add_handler(
        self,
        handler: TickHandler,
    ) -> None:
        """
        Register a handler that receives every new tick.
        """

        if handler not in self._handlers:
            self._handlers.append(handler)

            logger.debug(
                "Market-data handler registered: %s",
                getattr(
                    handler,
                    "__name__",
                    repr(handler),
                ),
            )

    def remove_handler(
        self,
        handler: TickHandler,
    ) -> None:
        """
        Remove a previously registered handler.
        """

        if handler in self._handlers:
            self._handlers.remove(handler)

    # =========================================================
    # Single tick
    # =========================================================

    def get_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """
        Retrieve one live tick from MT5 and normalize it
        into the AQE MarketTick model.
        """

        tick = self.broker.get_tick(symbol)

        if tick is None:
            logger.warning(
                "No tick received for symbol %s",
                symbol,
            )
            return None

        data = tick._asdict()

        return MarketTick(
            symbol=symbol,
            timestamp=int(
                data.get(
                    "time",
                    time.time(),
                )
            ),
            bid=float(
                data.get(
                    "bid",
                    0.0,
                )
            ),
            ask=float(
                data.get(
                    "ask",
                    0.0,
                )
            ),
            last=float(
                data.get(
                    "last",
                    0.0,
                )
            ),
            volume=int(
                data.get(
                    "volume",
                    0,
                )
            ),
            volume_real=float(
                data.get(
                    "volume_real",
                    0.0,
                )
            ),
        )

    # =========================================================
    # Redis publishing
    # =========================================================

    async def _publish_redis(
        self,
        tick: MarketTick,
    ) -> None:
        """
        Publish a normalized market tick to Redis Streams.

        Redis failures are isolated from the local market-data
        pipeline so that a temporary Redis outage does not stop
        MT5 market-data polling.
        """

        try:
            # The Bridge runs outside Docker, while Redis runs
            # inside Docker and exposes port 6379 to the host.
            #
            # connect() is idempotent, so calling it here is safe.
            await redis_client.connect()

            message_id = await redis_publisher.publish(
                self.REDIS_EVENT_TYPE,
                tick.model_dump(
                    mode="json",
                ),
                stream=self.REDIS_STREAM,
            )

            logger.debug(
                "Market tick published to Redis: " "stream=%s symbol=%s message_id=%s",
                self.REDIS_STREAM,
                tick.symbol,
                message_id,
            )

        except Exception:
            logger.exception(
                "Failed to publish market tick to Redis "
                "for %s. Local handlers will continue.",
                tick.symbol,
            )

    # =========================================================
    # Publishing
    # =========================================================

    async def _publish(
        self,
        tick: MarketTick,
    ) -> None:
        """
        Publish a normalized tick to:

        1. Redis Streams.
        2. Registered local handlers.

        Redis failures do not prevent local handlers from
        receiving the tick.
        """

        # -----------------------------------------------------
        # Distributed publication
        # -----------------------------------------------------

        await self._publish_redis(tick)

        # -----------------------------------------------------
        # Local in-process publication
        # -----------------------------------------------------

        for handler in list(self._handlers):
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
    # Polling
    # =========================================================

    async def _poll(self) -> None:
        """
        Continuously poll MT5 for subscribed symbols.
        """

        logger.info(
            "Market-data polling started " "(interval=%s seconds)",
            self.poll_interval,
        )

        while self._running:

            if not self._symbols:
                await asyncio.sleep(
                    self.poll_interval,
                )
                continue

            for symbol in list(self._symbols):

                if not self._running:
                    break

                try:
                    tick = self.get_tick(symbol)

                    if tick is None:
                        continue

                    previous = self._last_ticks.get(symbol)

                    # Do not publish the exact same tick repeatedly.
                    if previous == tick:
                        continue

                    self._last_ticks[symbol] = tick

                    await self._publish(tick)

                except Exception:
                    logger.exception(
                        "Market-data polling failed " "for %s",
                        symbol,
                    )

            await asyncio.sleep(
                self.poll_interval,
            )

        logger.info(
            "Market-data polling stopped.",
        )

    # =========================================================
    # Lifecycle
    # =========================================================

    def start(self) -> None:
        """
        Start the background market-data polling task.
        """

        if self._running:
            logger.warning(
                "Market-data service is already running.",
            )
            return

        self._running = True

        self._task = asyncio.create_task(
            self._poll(),
        )

        logger.info(
            "Market-data service started.",
        )

    async def stop(self) -> None:
        """
        Stop the background market-data polling task.
        """

        if not self._running:
            return

        self._running = False

        if self._task is not None:

            self._task.cancel()

            try:
                await self._task

            except asyncio.CancelledError:
                pass

            finally:
                self._task = None

        logger.info(
            "Market-data service stopped.",
        )

    # =========================================================
    # State
    # =========================================================

    @property
    def running(self) -> bool:
        """
        Return whether the service is currently running.
        """

        return self._running

    def last_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """
        Return the most recently received tick
        for a subscribed symbol.
        """

        return self._last_ticks.get(symbol)


market_data_service = MarketDataService(
    poll_interval=0.1,
)
