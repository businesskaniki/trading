import asyncio
import inspect
import math
import time
from typing import Awaitable, Callable

from app.broker.market_data import MarketDataBroker
from app.core.logging import logger
from app.infrastructure.redis import redis_publisher
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

    def subscribe(self, symbol: str) -> None:
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
        self._symbols.discard(symbol)
        self._last_ticks.pop(symbol, None)

        logger.info(
            "Market-data subscription removed: %s",
            symbol,
        )

    def subscriptions(self) -> list[str]:
        return sorted(self._symbols)

    def add_handler(self, handler: TickHandler) -> None:
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

    def remove_handler(self, handler: TickHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    @staticmethod
    def _validate_normalized_tick(
        tick: MarketTick,
    ) -> bool:
        """
        Defensive validation immediately before publication.

        This protects Redis even if the broker implementation
        changes or another broker implementation is introduced.
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

    def get_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """
        Retrieve one live tick from MT5 and normalize it
        into the AQE MarketTick model.

        Invalid broker data is rejected and never converted
        into fake zero-valued market data.
        """

        symbol = symbol.strip()

        if not symbol:
            logger.warning(
                "Cannot retrieve tick: empty symbol.",
            )
            return None

        tick = self.broker.get_tick(symbol)

        if tick is None:
            return None

        try:
            data = tick._asdict()
        except AttributeError:
            logger.exception(
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
        except (TypeError, ValueError):
            logger.exception(
                "Failed to normalize MT5 tick for %s: raw_tick=%r",
                symbol,
                data,
            )
            return None

        if not self._validate_normalized_tick(normalized):
            return None

        return normalized

    async def _publish_redis(
        self,
        tick: MarketTick,
    ) -> None:
        try:
            message_id = await redis_publisher.publish(
                self.REDIS_EVENT_TYPE,
                tick.model_dump(mode="json"),
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
                "Failed to publish market tick to Redis for %s. "
                "Local handlers will continue.",
                tick.symbol,
            )

    async def _publish(
        self,
        tick: MarketTick,
    ) -> None:
        if not self._validate_normalized_tick(tick):
            return

        await self._publish_redis(tick)

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

    async def _poll(self) -> None:
        logger.info(
            "Market-data polling started " "(interval=%s seconds)",
            self.poll_interval,
        )

        while self._running:
            if not self._symbols:
                await asyncio.sleep(self.poll_interval)
                continue

            for symbol in list(self._symbols):
                if not self._running:
                    break

                try:
                    tick = self.get_tick(symbol)

                    if tick is None:
                        continue

                    previous = self._last_ticks.get(symbol)

                    if previous == tick:
                        continue

                    self._last_ticks[symbol] = tick

                    await self._publish(tick)

                except Exception:
                    logger.exception(
                        "Market-data polling failed for %s",
                        symbol,
                    )

            await asyncio.sleep(self.poll_interval)

        logger.info("Market-data polling stopped.")

    def start(self) -> None:
        if self._running:
            logger.warning("Market-data service is already running.")
            return

        self._running = True

        self._task = asyncio.create_task(self._poll())

        logger.info("Market-data service started.")

    async def stop(self) -> None:
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

        logger.info("Market-data service stopped.")

    @property
    def running(self) -> bool:
        return self._running

    def last_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        return self._last_ticks.get(symbol)


market_data_service = MarketDataService(
    poll_interval=0.1,
)
