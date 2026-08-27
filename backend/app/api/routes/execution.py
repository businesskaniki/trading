from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_execution_service

from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
)

from app.schemas.execution import ExecutionOrder

from app.services.execution_service import ExecutionService


router = APIRouter(
    prefix="/execution",
    tags=["execution"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# MARKET ORDER
# ==========================================================

@router.post("/orders")
async def execute_order(
    order: ExecutionOrder,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Execute a market order through the configured broker.
    """

    try:
        return await execution_service.execute_order(order)

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# PENDING ORDER
# ==========================================================

@router.post("/orders/pending")
async def create_pending_order(
    order: ExecutionOrder,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Create a LIMIT or STOP pending order.
    """

    try:
        return await execution_service.create_pending_order(order)

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# OPEN POSITIONS
# ==========================================================

@router.get("/positions")
async def get_positions(
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve currently open positions.
    """

    try:
        return await execution_service.get_positions()

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# GET SINGLE POSITION
# ==========================================================

@router.get("/positions/{position_id}")
async def get_position(
    position_id: int,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve a single open position.
    """

    try:
        return await execution_service.broker.get_position(
            position_id
        )

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# MODIFY POSITION
# ==========================================================

@router.patch("/positions/{position_id}")
async def modify_position(
    position_id: int,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Modify stop-loss and/or take-profit on an open position.
    """

    if stop_loss is None and take_profit is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of stop_loss or take_profit is required.",
        )

    try:
        return await execution_service.modify_position(
            position_id=position_id,
            sl=stop_loss,
            tp=take_profit,
        )

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# CLOSE POSITION
# ==========================================================

@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: int,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Close an open position.
    """

    try:
        return await execution_service.close_position(
            position_id
        )

    except BrokerPositionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# ORDER HISTORY
# ==========================================================

@router.get("/history/orders")
async def get_order_history(
    start: str,
    end: str,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve historical broker orders.
    """

    try:
        return await execution_service.get_order_history(
            start=start,
            end=end,
        )

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


# ==========================================================
# DEAL HISTORY
# ==========================================================

@router.get("/history/deals")
async def get_deal_history(
    start: str,
    end: str,
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve historical broker deals.
    """

    try:
        return await execution_service.get_deal_history(
            start=start,
            end=end,
        )

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc