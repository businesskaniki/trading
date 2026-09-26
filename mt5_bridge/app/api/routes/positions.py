from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.position import (
    PositionCloseResponse,
    PositionModifyRequest,
    PositionModifyResponse,
    PositionResponse,
)
from app.services.position_service import PositionService

router = APIRouter(
    prefix="/positions",
    tags=["Positions"],
)

service = PositionService()


@router.get(
    "",
    response_model=List[PositionResponse],
)
def list_positions() -> list[dict]:
    """
    Return all currently open MT5 positions.
    """
    try:
        return service.list_positions()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve positions: {exc}",
        ) from exc


@router.get(
    "/{ticket}",
    response_model=PositionResponse,
)
def get_position(ticket: int) -> dict:
    """
    Return one open MT5 position by position ticket.
    """
    try:
        position = service.get_position(ticket)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve position {ticket}: {exc}",
        ) from exc

    if position is None:
        raise HTTPException(
            status_code=404,
            detail=f"Position {ticket} not found",
        )

    return position


@router.get(
    "/symbol/{symbol}",
    response_model=List[PositionResponse],
)
def list_positions_by_symbol(symbol: str) -> list[dict]:
    """
    Return all open positions for a broker symbol.
    """
    try:
        positions = service.by_symbol(symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(f"Failed to retrieve positions for " f"{symbol}: {exc}"),
        ) from exc

    return positions


@router.post(
    "/{ticket}/close",
    response_model=PositionCloseResponse,
)
def close_position(ticket: int) -> dict:
    """
    Close an open MT5 position by position ticket.

    The close operation generates a new broker order/deal.
    Those IDs are returned here when MT5 provides them.
    """
    try:
        result = service.close_position(ticket)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to close position {ticket}: {exc}",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Position {ticket} not found",
        )

    return {
        "ticket": result["ticket"],
        "symbol": result["symbol"],
        "volume": result["volume"],
        "retcode": result["retcode"],
        "comment": result.get("comment", ""),
        "order": result.get("order"),
        "deal": result.get("deal"),
        "position": result.get("position"),
    }


@router.patch(
    "/{ticket}",
    response_model=PositionModifyResponse,
)
def modify_position(
    ticket: int,
    request: PositionModifyRequest,
) -> dict:
    """
    Modify the SL and/or TP of an open MT5 position.
    """
    if request.sl is None and request.tp is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of sl or tp must be provided",
        )

    try:
        result = service.modify_position(
            ticket=ticket,
            sl=request.sl,
            tp=request.tp,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to modify position {ticket}: {exc}",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Position {ticket} not found",
        )

    return {
        "ticket": result["ticket"],
        "symbol": result["symbol"],
        "sl": result["sl"],
        "tp": result["tp"],
        "retcode": result["retcode"],
        "comment": result.get("comment", ""),
    }
