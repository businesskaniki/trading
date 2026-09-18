import asyncio
import inspect
import math
from datetime import datetime, timezone
from typing import Awaitable, Callable

import MetaTrader5 as mt5

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

    The service may start before MT5 is connected. In that case,
    polling remains idle until a valid MT5 terminal/account
    connection becomes available.

    Redis publish failures are tracked (see last_publish_error /
    last_publish_success_at) rather than only logged, so a broken
    Redis connection is visible through the API instead of requiring
    someone to tail server logs to notice ticks aren't actually
    reaching AQE.
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

        self._last_publish_error: str | None = None
        self._last_publish_error_at: datetime | None = None
        self._last_publish_success_at: datetime | None = None

    def subscribe(self, symbol: str) -> None:
        """
        Add a canonical broker symbol to the live market-data
        subscription set.

        Connection state is intentionally not checked here.
        A subscription can remain active while MT5 is temporarily
        disconnected and resume automatically after reconnection.
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
        Remove a symbol from live market-data collection.
        """

        symbol = symbol.strip()

        self._symbols.discard(symbol)
        self._last_ticks.pop(symbol, None)

        logger.info(
            "Market-data subscription removed: %s",
            symbol,
        )

    def subscriptions(self) -> list[str]:
        """
        Return subscribed symbols in deterministic order.
        """

        return sorted(self._symbols)

    def add_handler(self, handler: TickHandler) -> None:
        """
        Register an in-process market-data handler.
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

    def remove_handler(self, handler: TickHandler) -> None:
        """
        Remove a previously registered handler.
        """

        if handler in self._handlers:
            self._handlers.remove(handler)

    @staticmethod
    def _mt5_ready() -> bool:
        """
        Check whether MT5 is currently initialized, connected,
        and associated with an accessible account.

        Authentication remains the responsibility of the
        connection service.
        """

        terminal = mt5.terminal_info()

        if terminal is None:
            return False

        if not terminal.connected:
            return False

        account = mt5.account_info()

        if account is None:
            return False

        return True

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

        if not self._mt5_ready():
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
        """
        Publish a validated tick to Redis Streams.

        Failures are recorded on self._last_publish_error rather
        than only logged - a persistently failing Redis connection
        (e.g. never connected at startup) previously looked
        identical to a healthy one from the API's point of view,
        since ticks still reached _last_ticks and local handlers
        regardless of whether Redis received them.
        """

        try:
            message_id = await redis_publisher.publish(
                self.REDIS_EVENT_TYPE,
                tick.model_dump(mode="json"),
                stream=self.REDIS_STREAM,
            )

            self._last_publish_error = None
            self._last_publish_success_at = datetime.now(timezone.utc)

            logger.debug(
                "Market tick published to Redis: " "stream=%s symbol=%s message_id=%s",
                self.REDIS_STREAM,
                tick.symbol,
                message_id,
            )

        except Exception as exc:
            self._last_publish_error = str(exc)
            self._last_publish_error_at = datetime.now(timezone.utc)

            logger.exception(
                "Failed to publish market tick to Redis for %s. "
                "Local handlers will continue.",
                tick.symbol,
            )

    async def _publish(
        self,
        tick: MarketTick,
    ) -> None:
        """
        Publish a validated normalized tick to Redis and
        registered local handlers.
        """

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
        """
        Continuously poll subscribed symbols.

        MT5 may not yet be connected when this task starts.
        In that state the service waits without attempting to
        retrieve invalid ticks.

        Existing subscriptions remain intact across connection
        loss and recovery.
        """

        logger.info(
            "Market-data polling started " "(interval=%s seconds)",
            self.poll_interval,
        )

        connection_warning_logged = False

        while self._running:

            if not self._symbols:
                await asyncio.sleep(self.poll_interval)
                continue

            if not await asyncio.to_thread(self._mt5_ready):

                if not connection_warning_logged:
                    logger.warning(
                        "MT5 is not ready. "
                        "Market-data polling is waiting for a connection."
                    )
                    connection_warning_logged = True

                await asyncio.sleep(self.poll_interval)
                continue

            if connection_warning_logged:
                logger.info(
                    "MT5 connection is available. " "Market-data polling resumed."
                )
                connection_warning_logged = False

            for symbol in list(self._symbols):

                if not self._running:
                    break

                try:
                    tick = await asyncio.to_thread(self.get_tick, symbol)

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

        logger.info(
            "Market-data polling stopped.",
        )

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

        self._task = asyncio.create_task(self._poll())

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

    @property
    def running(self) -> bool:
        """
        Return whether the market-data polling task is running.
        """

        return self._running

    @property
    def last_publish_error(self) -> str | None:
        """
        Return the most recent Redis publish error, if any.

        None means either no publish has failed yet, or the most
        recent publish succeeded (a success clears this).
        """

        return self._last_publish_error

    @property
    def last_publish_error_at(self) -> datetime | None:
        """
        Return when the most recent Redis publish error occurred.
        """

        return self._last_publish_error_at

    @property
    def last_publish_success_at(self) -> datetime | None:
        """
        Return when a tick was last successfully published to Redis.

        Staying None while subscriptions/running are both truthy is
        the signature of exactly the bug this tracking exists to
        catch: MT5 data is flowing but nothing is reaching Redis.
        """

        return self._last_publish_success_at

    def last_tick(
        self,
        symbol: str,
    ) -> MarketTick | None:
        """
        Return the most recently published tick for a symbol.
        """

        return self._last_ticks.get(symbol)


market_data_service = MarketDataService(
    poll_interval=0.1,
)
