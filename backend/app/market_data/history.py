from sqlalchemy.dialects.postgresql import insert

from app.database.models.market_candle import MarketCandle
from app.database.session import SessionLocal
from app.market_data.service import market_data_service

TIMEFRAMES = ("M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1")


async def record_history(symbol: str, *, count: int = 5000) -> int:
    """Upsert broker candle history for every MT5 timeframe."""
    rows = []
    for timeframe in TIMEFRAMES:
        for candle in await market_data_service.get_candles(symbol, timeframe, count):
            rows.append({
                "symbol": candle.symbol, "timeframe": candle.timeframe,
                "timestamp": candle.timestamp, "open": candle.open, "high": candle.high,
                "low": candle.low, "close": candle.close, "volume": candle.volume,
                "spread": candle.spread,
            })
    if not rows:
        return 0
    async with SessionLocal() as db:
        statement = insert(MarketCandle).values(rows)
        await db.execute(statement.on_conflict_do_nothing(constraint="uq_market_candle"))
        await db.commit()
    return len(rows)
