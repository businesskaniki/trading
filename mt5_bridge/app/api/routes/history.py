from datetime import datetime
from typing import List

from fastapi import APIRouter

from app.schemas.history import (
    DealResponse,
    HistoryOrderResponse,
)

from app.services.history_service import HistoryService

router = APIRouter(
    prefix="/history",
    tags=["History"],
)

service = HistoryService()


@router.get(
    "/orders",
    response_model=List[HistoryOrderResponse],
)
def history_orders(
    start: datetime,
    end: datetime,
):

    return service.orders(
        start,
        end,
    )


@router.get(
    "/deals",
    response_model=List[DealResponse],
)
def history_deals(
    start: datetime,
    end: datetime,
):

    return service.deals(
        start,
        end,
    )