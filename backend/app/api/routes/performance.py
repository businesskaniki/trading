from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_performance_service,
)
from app.core.constants import PerformancePeriod
from app.schemas.performance import (
    PerformanceGenerateRequest,
    PerformanceResponse,
    PerformanceUpdate,
)
from app.services.performance_service import PerformanceService


router = APIRouter(
    prefix="/performance",
    tags=["performance"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# GENERATE PERFORMANCE
# ==========================================================

@router.post(
    "/generate",
    response_model=PerformanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_performance(
    payload: PerformanceGenerateRequest,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    """
    Generate a Performance snapshot from completed Trades.
    """

    if payload.end <= payload.start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be later than start",
        )

    try:
        return await service.generate_account_performance(
            account_id=payload.account_id,
            strategy_run_id=payload.strategy_run_id,
            period=payload.period,
            start=payload.start,
            end=payload.end,
            generated_at=payload.generated_at,
            starting_balance=payload.starting_balance,
            ending_balance=payload.ending_balance,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc



# LIST PERFORMANCE
# ==========================================================

@router.get(
    "/",
    response_model=list[PerformanceResponse],
)
async def list_performance(
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    return await service.get_all_performance()


# ==========================================================
# GET LATEST PERFORMANCE
# ==========================================================

@router.get(
    "/latest",
    response_model=PerformanceResponse | None,
)
async def get_latest_performance(
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    return await service.get_latest()


# ==========================================================
# GET BY STRATEGY RUN
# ==========================================================

@router.get(
    "/strategy/{strategy_run_id}",
    response_model=PerformanceResponse | None,
)
async def get_strategy_performance(
    strategy_run_id: UUID,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    return await service.get_strategy_performance(
        strategy_run_id
    )


# ==========================================================
# GET BY PERIOD
# ==========================================================

@router.get(
    "/period/{period}",
    response_model=list[PerformanceResponse],
)
async def get_by_period(
    period: PerformancePeriod,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    return await service.get_by_period(
        period
    )


# ==========================================================
# GET BY ID
# ==========================================================

@router.get(
    "/{performance_id}",
    response_model=PerformanceResponse,
)
async def get_performance(
    performance_id: UUID,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    try:
        return await service.get_performance(
            performance_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE PERFORMANCE
# ==========================================================

@router.patch(
    "/{performance_id}",
    response_model=PerformanceResponse,
)
async def update_performance(
    performance_id: UUID,
    payload: PerformanceUpdate,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    try:
        return await service.update_performance(
            performance_id,
            payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# DELETE PERFORMANCE
# ==========================================================

@router.delete(
    "/{performance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_performance(
    performance_id: UUID,
    service: PerformanceService = Depends(
        get_performance_service
    ),
):
    try:
        await service.delete_performance(
            performance_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc