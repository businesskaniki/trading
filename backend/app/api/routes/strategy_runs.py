from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_strategy_run_service
from app.schemas.strategy_run import (
    StrategyRunCreate,
    StrategyRunUpdate,
    StrategyRunResponse,
)
from app.core.constants import StrategyRunStatus, StrategyRunType

router = APIRouter(prefix="/strategy-runs", tags=["strategy_runs"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=StrategyRunResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy_run(
    payload: StrategyRunCreate,
    service=Depends(get_strategy_run_service),
):
    return await service.create_strategy_run(payload)


@router.get("/", response_model=list[StrategyRunResponse])
async def list_strategy_runs(service=Depends(get_strategy_run_service)):
    return await service.get_strategy_runs()


@router.get("/{strategy_run_id}", response_model=StrategyRunResponse)
async def get_strategy_run(strategy_run_id: str, service=Depends(get_strategy_run_service)):
    try:
        return await service.get_strategy_run(strategy_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/name/{strategy_name}", response_model=list[StrategyRunResponse])
async def list_by_name(strategy_name: str, service=Depends(get_strategy_run_service)):
    return await service.get_by_name(strategy_name)


@router.get("/status/{status}", response_model=list[StrategyRunResponse])
async def list_by_status(status: StrategyRunStatus, service=Depends(get_strategy_run_service)):
    return await service.get_by_status(status)


@router.get("/type/{run_type}", response_model=list[StrategyRunResponse])
async def list_by_type(run_type: StrategyRunType, service=Depends(get_strategy_run_service)):
    return await service.get_by_type(run_type)


@router.patch("/{strategy_run_id}", response_model=StrategyRunResponse)
async def update_strategy_run(
    strategy_run_id: str,
    payload: StrategyRunUpdate,
    service=Depends(get_strategy_run_service),
):
    try:
        return await service.update_strategy_run(strategy_run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{strategy_run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy_run(strategy_run_id: str, service=Depends(get_strategy_run_service)):
    try:
        await service.delete_strategy_run(strategy_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
