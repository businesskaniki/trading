from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from ..dependencies import (
    get_account_symbol_service,
    get_current_user,
)
from app.schemas.account_symbol import (
    AccountSymbolListResponse,
    AccountSymbolResponse,
    AccountSymbolSelection,
)
from app.services.account_symbol_service import AccountSymbolService

router = APIRouter(
    prefix="/trading-accounts/{account_id}/symbols",
    tags=["Account Symbols"],
)


# ==========================================================
# LIST ACCOUNT SYMBOLS
# ==========================================================


@router.get(
    "/",
    response_model=AccountSymbolListResponse,
)
async def list_account_symbols(
    account_id: UUID,
    current_user=Depends(get_current_user),
    service: AccountSymbolService = Depends(
        get_account_symbol_service,
    ),
):
    """
    Return all symbols available for a trading account.

    Symbols are populated by synchronization with the MT5
    bridge. The frontend uses this endpoint to display the
    account's available trading universe.
    """

    try:
        account_symbols = await service.list_account_symbols(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return AccountSymbolListResponse(
        items=account_symbols,
        total=len(account_symbols),
    )


# ==========================================================
# TRADING UNIVERSE
# ==========================================================


@router.get(
    "/universe",
    response_model=AccountSymbolListResponse,
)
async def get_trading_universe(
    account_id: UUID,
    current_user=Depends(get_current_user),
    service: AccountSymbolService = Depends(
        get_account_symbol_service,
    ),
):
    """
    Return only symbols explicitly enabled for algorithmic
    trading on this account.
    """

    try:
        universe = await service.get_trading_universe(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return AccountSymbolListResponse(
        items=universe,
        total=len(universe),
    )


# ==========================================================
# GET ONE ACCOUNT SYMBOL
# ==========================================================


@router.get(
    "/{account_symbol_id}",
    response_model=AccountSymbolResponse,
)
async def get_account_symbol(
    account_id: UUID,
    account_symbol_id: UUID,
    current_user=Depends(get_current_user),
    service: AccountSymbolService = Depends(
        get_account_symbol_service,
    ),
):
    """
    Return one account-symbol mapping.
    """

    try:
        account_symbol = await service.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Ensure the account-symbol belongs to the account in
    # the URL.
    if account_symbol.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account symbol not found.",
        )

    return account_symbol


# ==========================================================
# ENABLE / DISABLE SYMBOL
# ==========================================================


@router.patch(
    "/{account_symbol_id}/selection",
    response_model=AccountSymbolResponse,
)
async def update_account_symbol_selection(
    account_id: UUID,
    account_symbol_id: UUID,
    data: AccountSymbolSelection,
    current_user=Depends(get_current_user),
    service: AccountSymbolService = Depends(
        get_account_symbol_service,
    ),
):
    """
    Enable or disable a symbol for algorithmic trading
    on a specific trading account.

    This modifies only AccountSymbol.enabled.
    """

    try:
        account_symbol = await service.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if account_symbol.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account symbol not found.",
        )

    try:
        return await service.set_enabled(
            account_symbol_id=account_symbol_id,
            user_id=current_user.id,
            enabled=data.enabled,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# DELETE ACCOUNT SYMBOL
# ==========================================================


@router.delete(
    "/{account_symbol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account_symbol(
    account_id: UUID,
    account_symbol_id: UUID,
    current_user=Depends(get_current_user),
    service: AccountSymbolService = Depends(
        get_account_symbol_service,
    ),
):
    """
    Delete an account-symbol mapping.

    This is primarily an administrative/backend operation.
    The frontend symbol selector should normally use
    enable/disable rather than deletion.
    """

    try:
        account_symbol = await service.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if account_symbol.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account symbol not found.",
        )

    try:
        await service.delete_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return None
