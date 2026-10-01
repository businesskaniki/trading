from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_strategy_run_service,
)
from app.core.constants import StrategyRunStatus, StrategyRunType
from app.schemas.strategy_run import (
    StrategyRunCreate,
    StrategyRunResponse,
    StrategyRunUpdate,
)

router = APIRouter(
    prefix="/strategy-runs",
    tags=["strategy_runs"],
)


# ==========================================================
# CREATE STRATEGY RUN
# ==========================================================


@router.post(
    "",
    response_model=StrategyRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy_run(
    payload: StrategyRunCreate,
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    Create a new account-specific strategy run.

    The service is responsible for:
    - validating the strategy definition,
    - validating account ownership,
    - taking strategy name/version snapshots from the catalog,
    - validating the requested run configuration.
    """
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
    "",
    response_model=list[StrategyRunResponse],
)
async def list_strategy_runs(
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    List all strategy runs belonging to the authenticated user.
    """
    return await service.get_strategy_runs(
        user_id=current_user.id,
    )


# ==========================================================
# LIST BY NAME
# ==========================================================


@router.get(
    "/name/{strategy_name}",
    response_model=list[StrategyRunResponse],
)
async def list_by_name(
    strategy_name: str,
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    List strategy runs using the stored strategy-name snapshot.

    This is a query convenience endpoint. Strategy definition identity
    is authoritative through strategy_definition_id.
    """
    return await service.get_by_name(
        strategy_name,
        user_id=current_user.id,
    )


# ==========================================================
# LIST BY STATUS
# ==========================================================


@router.get(
    "/status/{run_status}",
    response_model=list[StrategyRunResponse],
)
async def list_by_status(
    run_status: StrategyRunStatus,
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    List strategy runs filtered by lifecycle status.
    """
    return await service.get_by_status(
        run_status,
        user_id=current_user.id,
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
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    List strategy runs filtered by run type.
    """
    return await service.get_by_type(
        run_type,
        user_id=current_user.id,
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
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    Retrieve one strategy run owned by the authenticated user.
    """
    try:
        return await service.get_strategy_run(
            strategy_run_id,
            user_id=current_user.id,
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
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    Update mutable configuration/state for a strategy run.

    Strategy definition identity and account assignment are immutable
    and are enforced by the service layer.
    """
    try:
        return await service.update_strategy_run(
            strategy_run_id,
            payload,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    current_user=Depends(get_current_user),
    service=Depends(get_strategy_run_service),
):
    """
    Delete a strategy run owned by the authenticated user.
    """
    try:
        await service.delete_strategy_run(
            strategy_run_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc