from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.schemas.symbol import (
    CandleResponse,
    SymbolResponse,
    TickResponse,
)

from app.services.symbol_service import SymbolService


router = APIRouter(
    prefix="/symbols",
    tags=["Symbols"],
)

service = SymbolService()


@router.get(
    "",
    response_model=List[SymbolResponse],
)
def list_symbols():

    try:
        return service.list_symbols()

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve symbols.",
        )


@router.get(
    "/{symbol}",
    response_model=SymbolResponse,
)
def get_symbol(symbol: str):

    try:

        data = service.get_symbol(symbol)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail="Symbol not found",
            )

        return data

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve symbol.",
        )


@router.get(
    "/{symbol}/tick",
    response_model=TickResponse,
)
def get_tick(symbol: str):

    try:

        tick = service.get_tick(symbol)

        if tick is None:
            raise HTTPException(
                status_code=404,
                detail="Tick not available",
            )

        return tick

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve tick.",
        )


@router.get(
    "/{symbol}/candles",
    response_model=List[CandleResponse],
)
def get_candles(
    symbol: str,
    timeframe: str = Query(
        "M15",
        description="One of M1, M5, M15, M30, H1, H4, D1",
    ),
    count: int = Query(
        200,
        le=1000,
        description="Number of most recent candles to return",
    ),
):

    try:

        candles = service.get_candles(
            symbol,
            timeframe,
            count,
        )

        if candles is None:
            raise HTTPException(
                status_code=404,
                detail="Candles not available",
            )

        return candles

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve candles.",
        )