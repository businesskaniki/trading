
import MetaTrader5 as mt5

from fastapi import APIRouter, HTTPException, Query

from app.broker.market_data import MarketDataBroker
from app.schemas.market_data import MarketTick
from app.services.market_data_service import market_data_service


router = APIRouter(
    prefix="/market-data",
    tags=["Market Data"],
)


broker = MarketDataBroker()


@router.get(
    "/tick/{symbol}",
    response_model=MarketTick,
)
def get_tick(symbol: str):
    """
    Return the latest market tick directly from MT5.
    """

    symbol = symbol.strip()

    tick = broker.get_tick(symbol)

    if tick is None:
        raise HTTPException(
            status_code=404,
            detail=f"No market tick available for {symbol}.",
        )

    data = tick._asdict()

    return MarketTick(
        symbol=symbol,
        timestamp=int(
            data.get(
                "time",
                0,
            )
        ),
        bid=float(
            data.get(
                "bid",
                0.0,
            )
        ),
        ask=float(
            data.get(
                "ask",
                0.0,
            )
        ),
        last=float(
            data.get(
                "last",
                0.0,
            )
        ),
        volume=int(
            data.get(
                "volume",
                0,
            )
        ),
        volume_real=float(
            data.get(
                "volume_real",
                0.0,
            )
        ),
    )


@router.post(
    "/subscribe/{symbol}",
)
def subscribe_symbol(symbol: str):
    """
    Subscribe a broker symbol to the live market-data service.

    Broker symbols are treated as canonical identifiers.
    Their casing is preserved because MT5 broker symbols can
    contain case-sensitive suffixes such as XAUUSD.s.
    """

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    info = mt5.symbol_info(symbol)

    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol not found: {symbol}",
        )

    if not info.visible:
        selected = mt5.symbol_select(
            symbol,
            True,
        )

        if not selected:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unable to select symbol {symbol}: "
                    f"{mt5.last_error()}"
                ),
            )

    market_data_service.subscribe(symbol)

    return {
        "success": True,
        "symbol": symbol,
        "subscribed": True,
        "subscriptions": (
            market_data_service.subscriptions()
        ),
    }


@router.delete(
    "/subscribe/{symbol}",
)
def unsubscribe_symbol(symbol: str):
    """
    Remove a symbol from the live market-data service.
    """

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    market_data_service.unsubscribe(symbol)

    return {
        "success": True,
        "symbol": symbol,
        "subscribed": False,
        "subscriptions": (
            market_data_service.subscriptions()
        ),
    }


@router.get(
    "/subscriptions",
)
def get_subscriptions():
    """
    Return the current market-data service state
    and subscribed symbols.
    """

    return {
        "running": market_data_service.running,
        "subscriptions": (
            market_data_service.subscriptions()
        ),
    }


@router.get(
    "/latest/{symbol}",
    response_model=MarketTick,
)
def get_latest_tick(symbol: str):
    """
    Return the latest tick collected by the continuous
    market-data service.
    """

    symbol = symbol.strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    tick = market_data_service.last_tick(symbol)

    if tick is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No streamed tick available for {symbol}."
            ),
        )

    return tick


@router.get(
    "/candles/{symbol}",
)
def get_candles(
    symbol: str,
    timeframe: str = Query(
        default="M1",
        description=(
            "MT5 timeframe: "
            "M1, M5, M15, M30, H1, H4, D1"
        ),
    ),
    count: int = Query(
        default=100,
        ge=1,
        le=5000,
    ),
):
    """
    Return historical OHLCV candles directly from MT5.
    """

    symbol = symbol.strip()
    timeframe = timeframe.upper().strip()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol cannot be empty.",
        )

    timeframe_map = {
        name: getattr(mt5, f"TIMEFRAME_{name}")
        for name in ("M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1")
        if hasattr(mt5, f"TIMEFRAME_{name}")
    }

    mt5_timeframe = timeframe_map.get(
        timeframe
    )

    if mt5_timeframe is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe: {timeframe}",
        )

    rates = broker.get_candles(
        symbol=symbol,
        timeframe=mt5_timeframe,
        count=count,
    )

    if rates is None:
        raise HTTPException(
            status_code=404,
            detail=f"No candles available for {symbol}.",
        )

    candles = []

    for rate in rates:
        candles.append(
            {
                "time": int(
                    rate["time"]
                ),
                "open": float(
                    rate["open"]
                ),
                "high": float(
                    rate["high"]
                ),
                "low": float(
                    rate["low"]
                ),
                "close": float(
                    rate["close"]
                ),
                "volume": int(
                    rate["tick_volume"]
                ),
                "spread": int(
                    rate["spread"]
                ),
            }
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
    }
