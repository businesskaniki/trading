from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_order_service
from app.schemas.order import OrderCreate, OrderUpdate, OrderResponse
from app.core.constants import OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, service=Depends(get_order_service)):
    try:
        return await service.create_order(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[OrderResponse])
async def list_orders(service=Depends(get_order_service)):
    return await service.get_orders()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, service=Depends(get_order_service)):
    try:
        return await service.get_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    payload: OrderUpdate,
    service=Depends(get_order_service),
):
    try:
        return await service.update_order(order_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    status: OrderStatus,
    service=Depends(get_order_service),
):
    try:
        return await service.update_order_status(order_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: str, service=Depends(get_order_service)):
    try:
        await service.delete_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
