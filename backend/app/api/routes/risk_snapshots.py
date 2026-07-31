from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_risk_snapshot_service
from app.schemas.snapshot import (
    RiskSnapshotCreate,
    RiskSnapshotResponse,
    RiskSnapshotUpdate,
)

router = APIRouter(prefix="/risk-snapshots", tags=["risk_snapshots"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=RiskSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    payload: RiskSnapshotCreate,
    service=Depends(get_risk_snapshot_service),
):
    try:
        return await service.create_snapshot(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[RiskSnapshotResponse])
async def list_snapshots(service=Depends(get_risk_snapshot_service)):
    return await service.get_snapshots()


@router.get("/{snapshot_id}", response_model=RiskSnapshotResponse)
async def get_snapshot(snapshot_id: str, service=Depends(get_risk_snapshot_service)):
    try:
        return await service.get_snapshot(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{snapshot_id}", response_model=RiskSnapshotResponse)
async def update_snapshot(
    snapshot_id: str,
    payload: RiskSnapshotUpdate,
    service=Depends(get_risk_snapshot_service),
):
    try:
        return await service.update_snapshot(snapshot_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(snapshot_id: str, service=Depends(get_risk_snapshot_service)):
    try:
        await service.delete_snapshot(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
