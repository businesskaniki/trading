from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_execution_service

from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
)

from app.schemas.execution import ExecutionOrder

from app.services.execution_service import ExecutionService


router = APIRouter(
    prefix="/execution",
    tags=["execution"],
)


# ==========================================================
# Execute Order
# ==========================================================

@router.post("/orders")
async def execute_order(
    order: ExecutionOrder,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    try:
        return await execution_service.execute_order(order)

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# Get Positions
# ==========================================================

@router.get("/positions")
async def get_positions(
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    try:
        return await execution_service.get_positions()

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# Close Position
# ==========================================================

@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: int,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    try:
        return await execution_service.close_position(
            position_id
        )

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc