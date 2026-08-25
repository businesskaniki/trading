from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_order_service,
    get_order_execution_service,
)

from app.core.constants import OrderStatus

from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
)

from app.services.order_service import OrderService
from app.services.order_execution_service import OrderExecutionService


router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# CREATE ORDER
# ==========================================================

@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    service: OrderService = Depends(get_order_service),
):
    try:
        return await service.create_order(payload)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# LIST ORDERS
# ==========================================================

@router.get(
    "/",
    response_model=list[OrderResponse],
)
async def list_orders(
    service: OrderService = Depends(get_order_service),
):
    return await service.get_orders()


# ==========================================================
# GET ORDER
# ==========================================================

@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
async def get_order(
    order_id: UUID,
    service: OrderService = Depends(get_order_service),
):
    try:
        return await service.get_order(order_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE ORDER
# ==========================================================

@router.patch(
    "/{order_id}",
    response_model=OrderResponse,
)
async def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    service: OrderService = Depends(get_order_service),
):
    try:
        return await service.update_order(
            order_id,
            payload,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Order not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# UPDATE ORDER STATUS
# ==========================================================

@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
)
async def update_order_status(
    order_id: UUID,
    status_value: OrderStatus,
    service: OrderService = Depends(get_order_service),
):
    try:
        return await service.update_order_status(
            order_id,
            status_value,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Order not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# EXECUTE ORDER
# ==========================================================

@router.post(
    "/{order_id}/execute",
    response_model=OrderResponse,
)
async def execute_order(
    order_id: UUID,
    service: OrderExecutionService = Depends(
        get_order_execution_service
    ),
):
    try:
        return await service.execute_order(order_id)

    except ValueError as exc:
        message = str(exc)

        if message == "Order not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# DELETE ORDER
# ==========================================================

@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_order(
    order_id: UUID,
    service: OrderService = Depends(get_order_service),
):
    try:
        await service.delete_order(order_id)

    except ValueError as exc:
        message = str(exc)

        if message == "Order not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    return None