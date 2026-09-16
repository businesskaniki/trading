import asyncio
import os

for key, value in {
    "SECRET_KEY": "test-secret", "POSTGRES_HOST": "localhost", "POSTGRES_DB": "test",
    "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "REDIS_HOST": "localhost",
    "SMTP_HOST": "localhost", "SMTP_USERNAME": "test", "SMTP_PASSWORD": "test",
    "SMTP_FROM_EMAIL": "test@example.com",
}.items():
    os.environ.setdefault(key, value)

from app.events.market import MarketTickEvent
from app.market_data.live import LiveTickHub
from app.market_data.models import MarketTick


def test_live_tick_hub_fans_out_only_matching_symbol():
    async def run():
        hub = LiveTickHub()
        await hub.start()
        queue = hub.subscribe("EURUSD")
        tick = MarketTick("EURUSD", 1, 1.1, 1.2)
        await hub._on_tick(MarketTickEvent.create(tick=tick))
        assert await queue.get() == tick
        hub.unsubscribe("EURUSD", queue)
        await hub.stop()

    asyncio.run(run())
