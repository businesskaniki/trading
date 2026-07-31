from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_position_service
from app.schemas.position import PositionCreate, PositionUpdate, PositionResponse
from app.core.constants import PositionStatus

router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(payload: PositionCreate, service=Depends(get_position_service)):
    try:
        return await service.create_position(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[PositionResponse])
async def list_positions(service=Depends(get_position_service)):
    return await service.get_positions()


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: str, service=Depends(get_position_service)):
    try:
        return await service.get_position(position_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{position_id}", response_model=PositionResponse)
async def update_position(
    position_id: str,
    payload: PositionUpdate,
    service=Depends(get_position_service),
):
    try:
        return await service.update_position(position_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{position_id}/status", response_model=PositionResponse)
async def update_position_status(
    position_id: str,
    status: PositionStatus,
    service=Depends(get_position_service),
):
    try:
        return await service.update_position_status(position_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(position_id: str, service=Depends(get_position_service)):
    try:
        await service.delete_position(position_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
