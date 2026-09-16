import asyncio

from app.core.celery import celery_app
from app.market_data.history import record_history


@celery_app.task(name="aqe.market_data.record_history")
def record_market_history(symbol: str, count: int = 5000) -> int:
    """Fetch and persist every supported MT5 timeframe for one symbol."""
    return asyncio.run(record_history(symbol, count=count))
