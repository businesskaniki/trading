from __future__ import annotations

import asyncio
from collections import defaultdict

from app.events import MarketTickEvent, event_bus


class LiveTickHub:
    """Fan out Redis-consumed MT5 ticks to all local WebSocket clients."""
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._started = False

    async def start(self) -> None:
        if not self._started:
            await event_bus.subscribe(MarketTickEvent, self._on_tick)
            self._started = True

    async def stop(self) -> None:
        if self._started:
            await event_bus.unsubscribe(MarketTickEvent, self._on_tick)
            self._queues.clear()
            self._started = False

    async def _on_tick(self, event: MarketTickEvent) -> None:
        for queue in list(self._queues[event.symbol]):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event.tick)

    def subscribe(self, symbol: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._queues[symbol].add(queue)
        return queue

    def unsubscribe(self, symbol: str, queue: asyncio.Queue) -> None:
        self._queues[symbol].discard(queue)
        if not self._queues[symbol]:
            self._queues.pop(symbol, None)


live_tick_hub = LiveTickHub()
