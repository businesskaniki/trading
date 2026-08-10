from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_broker_manager
from app.broker.broker_manager import BrokerManager
from app.broker.exceptions import BrokerConnectionError


router = APIRouter(
    prefix="/broker",
    tags=["broker"],
)


@router.get("/account")
async def get_broker_account(
    broker: BrokerManager = Depends(get_broker_manager),
):
    """
    Get the currently connected broker account.
    """

    try:
        return await broker.get_account()

    except BrokerConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc