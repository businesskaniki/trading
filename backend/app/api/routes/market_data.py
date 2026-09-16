from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.market_data.service import MarketDataError, MarketDataService

router = APIRouter(
    prefix="/market-data",
    tags=["Market Data"],
)

market_data_service = MarketDataService()


@router.get("/tick/{symbol}")
async def get_tick(symbol: str):
    """
    Retrieve the current broker tick for a symbol.
    """

    try:
        tick = await market_data_service.get_tick(symbol)

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    return {
        "symbol": tick.symbol,
        "timestamp": tick.timestamp,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": tick.volume,
        "volume_real": tick.volume_real,
        "spread": tick.spread,
        "mid": tick.mid,
        "datetime": tick.datetime.isoformat(),
    }


@router.get("/latest/{symbol}")
async def get_latest_tick(symbol: str):
    """
    Retrieve the latest tick stored by the MT5 bridge
    market-data streaming service.
    """

    try:
        tick = await market_data_service.get_latest_tick(symbol)

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    return {
        "symbol": tick.symbol,
        "timestamp": tick.timestamp,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": tick.volume,
        "volume_real": tick.volume_real,
        "spread": tick.spread,
        "mid": tick.mid,
        "datetime": tick.datetime.isoformat(),
    }


@router.post("/subscribe/{symbol}")
async def subscribe_symbol(symbol: str):
    """
    Subscribe the MT5 bridge market-data service to a symbol.
    """

    try:
        return await market_data_service.subscribe(symbol)

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.delete("/subscribe/{symbol}")
async def unsubscribe_symbol(symbol: str):
    """
    Remove a symbol from the MT5 bridge market-data subscription set.
    """

    try:
        return await market_data_service.unsubscribe(symbol)

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get("/subscriptions")
async def get_subscriptions():
    """
    Retrieve the symbols currently subscribed to market-data streaming.
    """

    try:
        return await market_data_service.subscriptions()

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    timeframe: str = Query(
        default="M15",
        description="MT5 timeframe such as M1, M5, M15, M30, H1, H4 or D1.",
    ),
    count: int = Query(
        default=200,
        ge=1,
        le=5000,
    ),
):
    """
    Retrieve normalized historical candles.
    """

    try:
        candles = await market_data_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

    except MarketDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    return {
        "symbol": symbol.strip(),
        "timeframe": timeframe.strip().upper(),
        "count": len(candles),
        "candles": [
            {
                "timestamp": candle.timestamp,
                "datetime": candle.datetime.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "spread": candle.spread,
            }
            for candle in candles
        ],
    }
