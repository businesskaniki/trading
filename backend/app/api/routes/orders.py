from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    get_current_user,
    get_order_execution_service,
    get_order_service,
)
from app.core.constants import OrderStatus
from app.database.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.services.order_execution_service import OrderExecutionService
from app.services.order_service import OrderService

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


# ----------------------------------------------------------------------
# Create
# ----------------------------------------------------------------------


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    data: OrderCreate,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    Create an order in AQE.

    Creation does not submit anything to the broker.
    The new order starts in CREATED state.
    """

    try:
        return await service.create_order(
            data=data,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ----------------------------------------------------------------------
# List
# ----------------------------------------------------------------------


@router.get(
    "/",
    response_model=list[OrderResponse],
)
async def list_orders(
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    List orders belonging to the current user.
    """

    return await service.get_orders(
        skip=skip,
        limit=limit,
        user_id=current_user.id,
    )


# ----------------------------------------------------------------------
# Get
# ----------------------------------------------------------------------


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    Retrieve one order.
    """

    try:
        return await service.get_order(
            order_id=order_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ----------------------------------------------------------------------
# Update
# ----------------------------------------------------------------------


@router.patch(
    "/{order_id}",
    response_model=OrderResponse,
)
async def update_order(
    order_id: UUID,
    data: OrderUpdate,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    Update a local CREATED order.

    Orders already submitted to the broker cannot be modified through
    this CRUD endpoint.
    """

    try:
        return await service.update_order(
            order_id=order_id,
            data=data,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ----------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
)
async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdate,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    Administrative/internal status update.

    Normal broker-driven lifecycle transitions should use /execute or
    broker reconciliation instead.
    """

    try:
        return await service.update_status(
            order_id=order_id,
            data=data,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ----------------------------------------------------------------------
# Execute
# ----------------------------------------------------------------------


@router.post(
    "/{order_id}/execute",
    response_model=OrderResponse,
)
async def execute_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OrderExecutionService = Depends(
        get_order_execution_service,
    ),
):
    """
    Submit an AQE order to the broker.

    The execution service determines whether the order is MARKET,
    LIMIT, or STOP and routes it to the appropriate broker operation.
    """

    try:
        return await service.execute_order(
            order_id=order_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ----------------------------------------------------------------------
# Delete
# ----------------------------------------------------------------------


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """
    Delete an order that has not yet been submitted to the broker.
    """

    try:
        await service.delete_order(
            order_id=order_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc