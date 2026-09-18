from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_trade_service,
)
from app.core.constants import TradeResult
from app.schemas.trade import TradeResponse
from app.services.trade_service import TradeService

router = APIRouter(
    prefix="/trades",
    tags=["trades"],
    dependencies=[Depends(get_current_user)],
)


# ==========================================================
# LIST TRADES
# ==========================================================


@router.get(
    "/",
    response_model=list[TradeResponse],
)
async def list_trades(
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    return await service.get_trades(user_id=current_user.id)


# ==========================================================
# GET LATEST TRADE
# IMPORTANT: Must be before /{trade_id}
# ==========================================================


@router.get(
    "/latest",
    response_model=TradeResponse | None,
)
async def get_latest_trade(
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    trade = await service.get_latest_trade()
    if trade is not None and trade.account.user_id != current_user.id:
        return None
    return trade


# ==========================================================
# LIST TRADES BY RESULT
# ==========================================================


@router.get(
    "/result/{result}",
    response_model=list[TradeResponse],
)
async def list_by_result(
    result: TradeResult,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    return await service.get_result_trades(result, user_id=current_user.id)


# ==========================================================
# LIST TRADES BY ACCOUNT
# ==========================================================


@router.get(
    "/account/{account_id}",
    response_model=list[TradeResponse],
)
async def list_by_account(
    account_id: UUID,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    return await service.get_account_trades(account_id, user_id=current_user.id)


# ==========================================================
# LIST TRADES BY SYMBOL
# ==========================================================


@router.get(
    "/symbol/{symbol_id}",
    response_model=list[TradeResponse],
)
async def list_by_symbol(
    symbol_id: UUID,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    return await service.get_symbol_trades(symbol_id, user_id=current_user.id)


# ==========================================================
# LIST TRADES BY STRATEGY
# ==========================================================


@router.get(
    "/strategy/{strategy}",
    response_model=list[TradeResponse],
)
async def list_by_strategy(
    strategy: str,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    return await service.get_strategy_trades(strategy, user_id=current_user.id)


# ==========================================================
# GET TRADE BY POSITION
# ==========================================================


@router.get(
    "/position/{position_id}",
    response_model=TradeResponse,
)
async def get_trade_by_position(
    position_id: UUID,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    try:
        return await service.get_trade_by_position(position_id, user_id=current_user.id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# GET TRADE
# IMPORTANT: Dynamic catch-all route must be LAST
# ==========================================================


@router.get(
    "/{trade_id}",
    response_model=TradeResponse,
)
async def get_trade(
    trade_id: UUID,
    current_user=Depends(get_current_user),
    service: TradeService = Depends(get_trade_service),
):
    try:
        return await service.get_trade(trade_id, user_id=current_user.id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
