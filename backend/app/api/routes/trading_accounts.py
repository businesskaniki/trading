from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_trading_account_service
from app.database.models.user import User
from app.schemas.trading_account import (
    TradingAccountCreate,
    TradingAccountListResponse,
    TradingAccountResponse,
    TradingAccountUpdate,
)

router = APIRouter(prefix="/trading-accounts", tags=["trading_accounts"])


@router.post("/", response_model=TradingAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: TradingAccountCreate,
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    try:
        return await service.create_account(payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=TradingAccountListResponse)
async def list_accounts(
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    accounts = await service.get_accounts(current_user.id)
    return {"total": len(accounts), "items": accounts}


@router.get("/active", response_model=list[TradingAccountResponse])
async def list_active_accounts(
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    return await service.get_active_accounts(current_user.id)


@router.get("/demo", response_model=list[TradingAccountResponse])
async def list_demo_accounts(
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    return await service.get_demo_accounts(current_user.id)


@router.get("/live", response_model=list[TradingAccountResponse])
async def list_live_accounts(
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    return await service.get_live_accounts(current_user.id)


@router.get("/{account_id}", response_model=TradingAccountResponse)
async def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    try:
        return await service.get_account(account_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{account_id}", response_model=TradingAccountResponse)
async def update_account(
    account_id: str,
    payload: TradingAccountUpdate,
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    try:
        return await service.update_account(account_id, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    service=Depends(get_trading_account_service),
):
    try:
        await service.delete_account(account_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
