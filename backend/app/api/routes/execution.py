from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

from app.api.dependencies import (
    get_current_user,
    get_execution_service,
    get_trading_account_service,
)

from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
)

from app.schemas.execution import ExecutionOrder

from app.services.execution_service import ExecutionService
from app.services.trading_account_service import TradingAccountService


async def _validate_execution_account(
    order: ExecutionOrder,
    current_user,
    account_service: TradingAccountService,
    execution_service: ExecutionService,
):
    if order.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id is required for broker execution.",
        )
    return await _validate_execution_account_id(
        order.account_id,
        current_user,
        account_service,
        execution_service,
    )


async def _validate_execution_account_id(
    account_id: UUID,
    current_user,
    account_service: TradingAccountService,
    execution_service: ExecutionService,
):
    try:
        account = await account_service.get_owned_account(account_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not account.active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Trading account is inactive.")

    try:
        broker_account = await execution_service.broker.get_account()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to verify broker account.") from exc

    if broker_account.get("login") is not None and int(broker_account["login"]) != account.login:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Broker is connected to a different trading account.")
    if broker_account.get("server") is not None and broker_account["server"] != account.server:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Broker is connected to a different trading server.")
    return account


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
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Execute a market order through the configured broker.
    """

    try:
        await _validate_execution_account(order, current_user, account_service, execution_service)
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
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Create a LIMIT or STOP pending order.
    """

    try:
        await _validate_execution_account(order, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve currently open positions.
    """

    try:
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve a single open position.
    """

    try:
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
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
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Close an open position.
    """

    try:
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve historical broker orders.
    """

    try:
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
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
    account_id: UUID,
    current_user=Depends(get_current_user),
    account_service: TradingAccountService = Depends(get_trading_account_service),
    execution_service: ExecutionService = Depends(
        get_execution_service
    ),
):
    """
    Retrieve historical broker deals.
    """

    try:
        await _validate_execution_account_id(account_id, current_user, account_service, execution_service)
        return await execution_service.get_deal_history(
            start=start,
            end=end,
        )

    except BrokerOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc