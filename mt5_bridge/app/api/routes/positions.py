from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.position import PositionResponse
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
)
def close_position(ticket: int):

    try:

        result = service.close_position(ticket)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Position not found",
            )

        return result

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )