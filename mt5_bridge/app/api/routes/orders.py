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

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="Order submission failed.",
        )


@router.get(
    "",
    response_model=List[OrderResponse],
)
def list_orders():

    return service.list_orders()



@router.post(
    "/pending",
    response_model=OrderResponse,
)
def create_pending_order(request: OrderRequest):

    try:

        return service.create_pending_order(
            symbol=request.symbol,
            volume=request.volume,
            order_type=request.order_type,
            price=request.price,
            sl=request.sl,
            tp=request.tp,
            deviation=request.deviation,
            magic=request.magic,
            comment=request.comment,
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="Pending order submission failed.",
        )