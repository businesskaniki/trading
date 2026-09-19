from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_execution_service,
    get_trading_account_service,
)
from app.broker.exceptions import BrokerConnectionError
from app.services.execution_service import ExecutionService
from app.services.trading_account_service import TradingAccountService


router = APIRouter(
    prefix="/broker",
    tags=["broker"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/account")
async def get_broker_account(
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(get_execution_service),
):
    """
    Get the broker account info for one of the current user's
    trading accounts.

    account_id is now required, and ownership is verified before
    anything is returned - previously this endpoint had no account
    parameter at all and returned whatever account the globally
    configured broker happened to be connected to, regardless of
    who was asking or whether it was even theirs.
    """

    try:
        await account_service.get_owned_account(account_id, current_user.id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        return await execution_service.broker.get_account()

    except BrokerConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc