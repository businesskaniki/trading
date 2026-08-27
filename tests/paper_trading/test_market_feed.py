import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.market.feed import CandleAggregator, PollingCandleFeed
from engine.market.ticks import Tick


def tick(minute, second, price):
    return Tick(
        symbol="EURUSD",
        bid=Decimal(str(price)),
        ask=Decimal(str(price)),
        time=datetime(2026, 1, 1, 12, minute, second, tzinfo=timezone.utc),
    )


def test_aggregator_emits_completed_candle():
    aggregator = CandleAggregator(timedelta(minutes=1))

    assert aggregator.update(tick(0, 5, 100)) is None
    assert aggregator.update(tick(0, 30, 101)) is None
    candle = aggregator.update(tick(1, 0, 99))

    assert candle.open == Decimal("100")
    assert candle.high == Decimal("101")
    assert candle.low == Decimal("100")
    assert candle.close == Decimal("101")
    assert candle.volume == Decimal("2")


def test_polling_feed_yields_closed_candles():
    ticks = iter([tick(0, 5, 100), tick(1, 0, 101), tick(2, 0, 102)])

    async def source(symbol):
        return next(ticks)

    async def collect():
        feed = PollingCandleFeed(
            source,
            ["EURUSD"],
            timeframe=timedelta(minutes=1),
            poll_interval=0.001,
        )
        candles = []
        for _ in range(3):
            candles.extend(await feed.poll_once())
        return candles

    candles = asyncio.run(collect())

    assert len(candles) == 2
    assert candles[0].close == Decimal("100")
    assert candles[1].close == Decimal("101")