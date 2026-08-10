from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.order import (
    OrderRequest,
    OrderResponse,
)

from app.services.order_service import OrderService

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)

service = OrderService()


@router.post(
    "",
    response_model=OrderResponse,
)
def create_order(request: OrderRequest):

    try:

        return service.send_order(
            request.model_dump()
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=List[OrderResponse],
)
def list_orders():

    return service.list_orders()