from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from app.schemas.order import OrderRequest, OrderResponse
from app.services.order_service import OrderService

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)

service = OrderService()


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
)
def create_order(request: OrderRequest) -> OrderResponse:
    """
    Submit a market order to MetaTrader 5.
    """

    try:
        result = service.send_order(request.model_dump())
        return result

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Order submission failed.",
        ) from exc


@router.get(
    "",
    response_model=List[OrderResponse],
)
def list_orders() -> List[OrderResponse]:
    """
    Return currently active MT5 orders.
    """

    try:
        return service.list_orders()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to retrieve orders.",
        ) from exc


@router.post(
    "/pending",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
)
def create_pending_order(request: OrderRequest) -> OrderResponse:
    """
    Submit a pending order to MetaTrader 5.
    """

    try:
        result = service.create_pending_order(
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

        return result

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Pending order submission failed.",
        ) from exc
