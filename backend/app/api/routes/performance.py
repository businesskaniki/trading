from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_performance_service
from app.schemas.performance import (
    PerformanceCreate,
    PerformanceResponse,
    PerformanceUpdate,
)
from app.core.constants import PerformancePeriod

router = APIRouter(prefix="/performance", tags=["performance"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=PerformanceResponse, status_code=status.HTTP_201_CREATED)
async def create_performance(
    payload: PerformanceCreate,
    service=Depends(get_performance_service),
):
    try:
        return await service.create_performance(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[PerformanceResponse])
async def list_performance(service=Depends(get_performance_service)):
    return await service.get_all_performance()


@router.get("/{performance_id}", response_model=PerformanceResponse)
async def get_performance(performance_id: str, service=Depends(get_performance_service)):
    try:
        return await service.get_performance(performance_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/strategy/{strategy_run_id}", response_model=PerformanceResponse)
async def get_strategy_performance(strategy_run_id: str, service=Depends(get_performance_service)):
    return await service.get_strategy_performance(strategy_run_id)


@router.get("/period/{period}", response_model=list[PerformanceResponse])
async def get_by_period(period: PerformancePeriod, service=Depends(get_performance_service)):
    return await service.get_by_period(period)


@router.patch("/{performance_id}", response_model=PerformanceResponse)
async def update_performance(
    performance_id: str,
    payload: PerformanceUpdate,
    service=Depends(get_performance_service),
):
    try:
        return await service.update_performance(performance_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{performance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_performance(performance_id: str, service=Depends(get_performance_service)):
    try:
        await service.delete_performance(performance_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
