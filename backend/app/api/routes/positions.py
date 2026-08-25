from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_position_service,
    get_position_sync_service,
)
from app.core.constants import PositionStatus
from app.schemas.position import (
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)
from app.services.position_service import PositionService
from app.services.position_sync_service import PositionSyncService


router = APIRouter(
    prefix="/positions",
    tags=["positions"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# CREATE POSITION
# ==========================================================

@router.post(
    "/",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_position(
    payload: PositionCreate,
    service: PositionService = Depends(
        get_position_service
    ),
):
    try:
        return await service.create_position(payload)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# LIST POSITIONS
# ==========================================================

@router.get(
    "/",
    response_model=list[PositionResponse],
)
async def list_positions(
    service: PositionService = Depends(
        get_position_service
    ),
):
    return await service.get_positions()


# ==========================================================
# GET POSITION
# ==========================================================

@router.get(
    "/{position_id}",
    response_model=PositionResponse,
)
async def get_position(
    position_id: UUID,
    service: PositionService = Depends(
        get_position_service
    ),
):
    try:
        return await service.get_position(
            position_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE POSITION
# ==========================================================

@router.patch(
    "/{position_id}",
    response_model=PositionResponse,
)
async def update_position(
    position_id: UUID,
    payload: PositionUpdate,
    service: PositionService = Depends(
        get_position_service
    ),
):
    try:
        return await service.update_position(
            position_id,
            payload,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# UPDATE POSITION STATUS
# ==========================================================

@router.patch(
    "/{position_id}/status",
    response_model=PositionResponse,
)
async def update_position_status(
    position_id: UUID,
    status_value: PositionStatus,
    service: PositionService = Depends(
        get_position_service
    ),
):
    try:
        return await service.update_position_status(
            position_id,
            status_value,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# DELETE POSITION
# ==========================================================

@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_position(
    position_id: UUID,
    service: PositionService = Depends(
        get_position_service
    ),
):
    try:
        await service.delete_position(
            position_id
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    return None



# ==========================================================
# SYNC BROKER POSITIONS
# ==========================================================

@router.post(
    "/sync",
    response_model=list[PositionResponse],
)
async def sync_positions(
    service: PositionSyncService = Depends(
        get_position_sync_service
    ),
):
    try:
        return await service.sync_positions()

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc