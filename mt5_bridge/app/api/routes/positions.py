from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.position import (
    PositionResponse,
    PositionCloseResponse,
    PositionModifyRequest,
    PositionModifyResponse,
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
def list_positions():

    return service.list_positions()


@router.get(
    "/{ticket}",
    response_model=PositionResponse,
)
def get_position(ticket: int):

    position = service.get_position(ticket)

    if position is None:
        raise HTTPException(
            status_code=404,
            detail="Position not found",
        )

    return position


@router.post(
    "/{ticket}/close",
    response_model=PositionCloseResponse,
)
def close_position(ticket: int):

    try:

        result = service.close_position(ticket)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Position not found",
            )

        return {
            "ticket": ticket,
            "retcode": result["retcode"],
            "comment": result["comment"],
            "order": result["order"],
            "deal": result["deal"],
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

@router.patch(
    "/{ticket}",
)
def modify_position(
    ticket: int,
    request: PositionModifyRequest,
):

    try:

        result = service.modify_position(
            ticket=ticket,
            sl=request.sl,
            tp=request.tp,
        )

        if result is None:

            raise HTTPException(
                status_code=404,
                detail="Position not found",
            )

        return {
            "ticket": ticket,
            "retcode": result["retcode"],
            "comment": result["comment"],
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )