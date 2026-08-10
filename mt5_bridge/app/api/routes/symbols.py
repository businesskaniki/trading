from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.symbol import (
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

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
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

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
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

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )