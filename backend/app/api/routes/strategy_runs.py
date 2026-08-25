from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_strategy_run_service,
)
from app.core.constants import StrategyRunStatus, StrategyRunType
from app.schemas.strategy_run import (
    StrategyRunCreate,
    StrategyRunUpdate,
    StrategyRunResponse,
)


router = APIRouter(
    prefix="/strategy-runs",
    tags=["strategy_runs"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# CREATE STRATEGY RUN
# ==========================================================

@router.post(
    "/",
    response_model=StrategyRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy_run(
    payload: StrategyRunCreate,
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    try:
        return await service.create_strategy_run(
            payload,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# LIST STRATEGY RUNS
# ==========================================================

@router.get(
    "/",
    response_model=list[StrategyRunResponse],
)
async def list_strategy_runs(
    service=Depends(get_strategy_run_service),
):
    return await service.get_strategy_runs()


# ==========================================================
# LIST BY NAME
# ==========================================================

@router.get(
    "/name/{strategy_name}",
    response_model=list[StrategyRunResponse],
)
async def list_by_name(
    strategy_name: str,
    service=Depends(get_strategy_run_service),
):
    return await service.get_by_name(
        strategy_name
    )


# ==========================================================
# LIST BY STATUS
# ==========================================================

@router.get(
    "/status/{status}",
    response_model=list[StrategyRunResponse],
)
async def list_by_status(
    status: StrategyRunStatus,
    service=Depends(get_strategy_run_service),
):
    return await service.get_by_status(
        status
    )


# ==========================================================
# LIST BY TYPE
# ==========================================================

@router.get(
    "/type/{run_type}",
    response_model=list[StrategyRunResponse],
)
async def list_by_type(
    run_type: StrategyRunType,
    service=Depends(get_strategy_run_service),
):
    return await service.get_by_type(
        run_type
    )


# ==========================================================
# GET STRATEGY RUN
# ==========================================================

@router.get(
    "/{strategy_run_id}",
    response_model=StrategyRunResponse,
)
async def get_strategy_run(
    strategy_run_id: UUID,
    service=Depends(get_strategy_run_service),
):
    try:
        return await service.get_strategy_run(
            strategy_run_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE STRATEGY RUN
# ==========================================================

@router.patch(
    "/{strategy_run_id}",
    response_model=StrategyRunResponse,
)
async def update_strategy_run(
    strategy_run_id: UUID,
    payload: StrategyRunUpdate,
    service=Depends(get_strategy_run_service),
):
    try:
        return await service.update_strategy_run(
            strategy_run_id,
            payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# DELETE STRATEGY RUN
# ==========================================================

@router.delete(
    "/{strategy_run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_strategy_run(
    strategy_run_id: UUID,
    service=Depends(get_strategy_run_service),
):
    try:
        await service.delete_strategy_run(
            strategy_run_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc