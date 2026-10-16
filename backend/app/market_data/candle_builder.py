from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

from app.events import EventBus, event_bus
from app.events.market import MarketCandleEvent, MarketTickEvent
from app.market_data.models import MarketCandle, MarketTick

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _CandleState:
    """Mutable OHLC state for one symbol and timeframe."""

    bucket_start: int
    open: float
    high: float
    low: float
    close: float
    tick_count: int = 1

    # The first candle observed after startup may be incomplete.
    # Do not publish it as a completed candle.
    publishable: bool = False

    def update(self, price: float) -> None:
        """Incorporate one new price into the current candle."""

        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.tick_count += 1

    def to_candle(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> MarketCandle:
        """Create an immutable AQE candle snapshot."""

        return MarketCandle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=self.bucket_start,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.tick_count,
            # Broker point size is required to derive spread points
            # correctly. Do not mistake a price difference for points.
            spread=0,
        )


class LiveCandleBuilder:
    """
    Convert incoming AQE market ticks into completed OHLC candles.

    Data flow:

        MarketTickEvent
              |
              v
        LiveCandleBuilder
              |
              v
        Completed MarketCandle
              |
              v
        MarketCandleEvent
              |
              v
        StrategyDispatcher
              |
              v
        Candle-based strategy

    The builder performs no database queries and does not communicate
    with brokers. It uses the symbol identity carried by MarketTick.

    Candle timestamps are UTC Unix timestamps aligned to fixed-duration
    epoch buckets. This alignment is suitable for intraday timeframes
    whose boundaries match UTC epoch intervals. Broker-session
    alignment, especially for D1 candles, must be verified before
    relying on these synthetic candles for production trading.

    The first observed candle for each symbol/timeframe is deliberately
    discarded when its bucket closes because the builder might have
    started partway through that interval.

    Subsequent completed candles are published when a tick arrives in
    a newer bucket. No empty candles are synthesized across data gaps.

    This is a tick-derived candle builder; it does not replace the
    historical candle store used for strategy indicator warm-up.
    """

    TIMEFRAME_SECONDS: Final[dict[str, int]] = {
        "M1": 60,
        "M5": 5 * 60,
        "M15": 15 * 60,
        "M30": 30 * 60,
        "H1": 60 * 60,
        "H4": 4 * 60 * 60,
        "D1": 24 * 60 * 60,
    }

    DEFAULT_TIMEFRAMES: Final[tuple[str, ...]] = (
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "H4",
        "D1",
    )

    MAX_RECENT_EVENT_IDS: Final[int] = 10_000

    def __init__(
        self,
        *,
        bus: EventBus | None = None,
        timeframes: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        """Initialize the candle builder without starting it."""

        self._event_bus = bus if bus is not None else event_bus

        requested_timeframes = (
            self.DEFAULT_TIMEFRAMES if timeframes is None else timeframes
        )

        normalized: list[str] = []

        for timeframe in requested_timeframes:
            value = str(timeframe).strip().upper()

            if value not in self.TIMEFRAME_SECONDS:
                raise ValueError(
                    f"Unsupported live candle timeframe: {timeframe!r}. "
                    f"Supported values: {tuple(self.TIMEFRAME_SECONDS)}."
                )

            if value not in normalized:
                normalized.append(value)

        if not normalized:
            raise ValueError("LiveCandleBuilder requires at least one timeframe.")

        self.timeframes = tuple(normalized)

        # (canonical_symbol, timeframe) -> active candle state.
        self._states: dict[tuple[str, str], _CandleState] = {}

        # Bounded in-memory deduplication for Redis/event redelivery.
        self._recent_event_ids: OrderedDict[str, None] = OrderedDict()

        self._lock = asyncio.Lock()
        self._started = False

        self._ticks_received = 0
        self._candles_published = 0
        self._out_of_order_ticks = 0
        self._duplicate_events = 0
        self._invalid_ticks = 0

        self._last_error: str | None = None

    @property
    def started(self) -> bool:
        """Return whether the builder is subscribed to tick events."""

        return self._started

    async def start(self) -> None:
        """Subscribe to market ticks. Repeated calls are safe."""

        if self._started:
            return

        await self._event_bus.subscribe(
            MarketTickEvent,
            self._on_tick,
        )

        self._started = True

        logger.info(
            "Live candle builder started. timeframes=%s",
            self.timeframes,
        )

    async def stop(self) -> None:
        """Unsubscribe and clear in-memory candle state."""

        if not self._started:
            return

        await self._event_bus.unsubscribe(
            MarketTickEvent,
            self._on_tick,
        )

        async with self._lock:
            self._states.clear()
            self._recent_event_ids.clear()

        self._started = False

        logger.info(
            "Live candle builder stopped. " "ticks=%d candles=%d",
            self._ticks_received,
            self._candles_published,
        )

    async def _on_tick(self, event: MarketTickEvent) -> None:
        """
        Incorporate one MarketTickEvent and publish any newly completed
        candles to the same AQE EventBus.
        """

        if not isinstance(event, MarketTickEvent):
            return

        tick = event.tick

        if not isinstance(tick, MarketTick):
            self._invalid_ticks += 1
            logger.warning(
                "Ignoring invalid market tick object: type=%s",
                type(tick).__name__,
            )
            return

        validation_errors = tick.validation_errors()

        if validation_errors:
            self._invalid_ticks += 1
            logger.warning(
                "Ignoring invalid tick while building candles. " "symbol=%s errors=%s",
                tick.symbol,
                validation_errors,
            )
            return

        # Bid is the usual price basis for MT5-style bars. Fall back to
        # ask only when bid is unavailable or zero.
        price = tick.bid if tick.bid > 0 else tick.ask

        if price <= 0:
            self._invalid_ticks += 1
            return

        symbol = tick.symbol.strip()

        if not symbol:
            self._invalid_ticks += 1
            return

        event_id = str(event.event_id)
        completed: list[MarketCandle] = []

        async with self._lock:
            if event_id in self._recent_event_ids:
                self._duplicate_events += 1
                return

            self._remember_event_id(event_id)
            self._ticks_received += 1

            for timeframe in self.timeframes:
                duration = self.TIMEFRAME_SECONDS[timeframe]

                bucket_start = (tick.timestamp // duration) * duration

                key = (symbol, timeframe)
                state = self._states.get(key)

                if state is None:
                    # The builder could have started mid-candle.
                    self._states[key] = _CandleState(
                        bucket_start=bucket_start,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        tick_count=1,
                        publishable=False,
                    )
                    continue

                if bucket_start < state.bucket_start:
                    # An old tick must not roll the candle backwards.
                    self._out_of_order_ticks += 1
                    continue

                if bucket_start == state.bucket_start:
                    state.update(price)
                    continue

                # A tick from a later bucket closes the previous candle.
                if state.publishable:
                    candle = state.to_candle(
                        symbol=symbol,
                        timeframe=timeframe,
                    )

                    if not candle.validation_errors():
                        completed.append(candle)
                    else:
                        logger.warning(
                            "Completed live candle failed validation. "
                            "symbol=%s timeframe=%s errors=%s",
                            symbol,
                            timeframe,
                            candle.validation_errors(),
                        )

                # The new bucket becomes eligible for publication once
                # we have observed its transition from the prior bucket.
                self._states[key] = _CandleState(
                    bucket_start=bucket_start,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    tick_count=1,
                    publishable=True,
                )

        # Publish outside the lock so subscribers can process events
        # without blocking updates to other symbols/timeframes.
        for candle in completed:
            try:
                candle_event = MarketCandleEvent.create(
                    candle=candle,
                )

                await self._event_bus.publish(candle_event)

                self._candles_published += 1

                logger.info(
                    "Completed live candle published. "
                    "symbol=%s timeframe=%s timestamp=%s "
                    "open=%s high=%s low=%s close=%s ticks=%s",
                    candle.symbol,
                    candle.timeframe,
                    candle.timestamp,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                )

            except Exception as exc:
                self._last_error = str(exc)

                logger.exception(
                    "Failed to publish completed live candle. "
                    "symbol=%s timeframe=%s timestamp=%s",
                    candle.symbol,
                    candle.timeframe,
                    candle.timestamp,
                )

    def _remember_event_id(self, event_id: str) -> None:
        """Remember an event ID while bounding memory usage."""

        self._recent_event_ids[event_id] = None
        self._recent_event_ids.move_to_end(event_id)

        while len(self._recent_event_ids) > self.MAX_RECENT_EVENT_IDS:
            self._recent_event_ids.popitem(last=False)

    def status(self) -> dict[str, object]:
        """Return runtime diagnostics."""

        return {
            "started": self._started,
            "timeframes": list(self.timeframes),
            "active_candles": len(self._states),
            "ticks_received": self._ticks_received,
            "candles_published": self._candles_published,
            "duplicate_events": self._duplicate_events,
            "out_of_order_ticks": self._out_of_order_ticks,
            "invalid_ticks": self._invalid_ticks,
            "last_error": self._last_error,
        }


__all__ = ["LiveCandleBuilder"]
