"""Tick polling and deterministic candle aggregation."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.market.candles import Candle
from engine.market.ticks import Tick


class CandleAggregator:
    def __init__(self, timeframe: timedelta):
        if timeframe.total_seconds() <= 0:
            raise ValueError("timeframe must be positive")
        self.timeframe = timeframe
        self.current: Candle | None = None

    def update(self, tick: Tick) -> Candle | None:
        opened_at = self._bucket_start(tick.time)
        if self.current is None:
            self.current = self._new_candle(tick, opened_at)
            return None

        if opened_at == self.current.opened_at:
            self.current = Candle(
                symbol=self.current.symbol,
                timeframe=self._timeframe_name(),
                open=self.current.open,
                high=max(self.current.high, tick.mid),
                low=min(self.current.low, tick.mid),
                close=tick.mid,
                volume=self.current.volume + Decimal("1"),
                opened_at=self.current.opened_at,
            )
            return None

        closed = self.current
        self.current = self._new_candle(tick, opened_at)
        return closed

    def _bucket_start(self, timestamp: datetime) -> datetime:
        timestamp = timestamp.astimezone(timezone.utc)
        seconds = int(timestamp.timestamp())
        width = int(self.timeframe.total_seconds())
        return datetime.fromtimestamp(seconds - seconds % width, timezone.utc)

    def _new_candle(self, tick: Tick, opened_at: datetime) -> Candle:
        return Candle(
            symbol=tick.symbol,
            timeframe=self._timeframe_name(),
            open=tick.mid,
            high=tick.mid,
            low=tick.mid,
            close=tick.mid,
            volume=Decimal("1"),
            opened_at=opened_at,
        )

    def _timeframe_name(self) -> str:
        minutes = int(self.timeframe.total_seconds() // 60)
        return f"M{minutes}" if minutes else f"{int(self.timeframe.total_seconds())}S"


TickSource = Callable[[str], Awaitable[Tick]]


class PollingCandleFeed:
    """Poll a tick source and yield only completed candles."""

    def __init__(
        self,
        source: TickSource,
        symbols: Iterable[str],
        timeframe: timedelta = timedelta(minutes=1),
        poll_interval: float = 1.0,
    ):
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.source = source
        self.symbols = tuple(symbols)
        self.poll_interval = poll_interval
        self.aggregators = {
            symbol: CandleAggregator(timeframe) for symbol in self.symbols
        }

    async def poll_once(self) -> list[Candle]:
        candles = []
        for symbol in self.symbols:
            tick = await self.source(symbol)
            candle = self.aggregators[symbol].update(tick)
            if candle is not None:
                candles.append(candle)
        return candles

    async def run(self) -> AsyncIterator[Candle]:
        while True:
            for candle in await self.poll_once():
                yield candle
            await asyncio.sleep(self.poll_interval)