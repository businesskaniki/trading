from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import (
    get_current_user,
    get_mt5_bridge_service,
    get_symbol_sync_service,
    get_trading_account_service,
)

from app.services.symbol_sync_service import SymbolSyncError
from app.core.constants import AccountStatus
from app.database.models.user import User
from app.schemas.trading_account import (
    TradingAccountCreate,
    TradingAccountListResponse,
    TradingAccountResponse,
    TradingAccountStateUpdate,
    TradingAccountUpdate,
)
from app.services.mt5_bridge_service import (
    MT5BridgeError,
    MT5BridgeService,
)
from app.services.trading_account_service import TradingAccountService
from app.services.symbol_sync_service import (
    SymbolSyncError,
    SymbolSyncService,
)

router = APIRouter(
    prefix="/trading-accounts",
    tags=["Trading Accounts"],
)


# ============================================================
# CREATE
# ============================================================


@router.post(
    "/",
    response_model=TradingAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trading_account(
    data: TradingAccountCreate,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Create a trading account for the authenticated user.

    Broker credentials are encrypted by TradingAccountService
    before being persisted.
    """

    try:
        return await service.create_account(
            user_id=current_user.id,
            data=data,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ============================================================
# LIST
# ============================================================


@router.get(
    "/",
    response_model=TradingAccountListResponse,
)
async def list_trading_accounts(
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Return all trading accounts belonging to the authenticated user.
    """

    accounts = await service.list_accounts(
        user_id=current_user.id,
    )

    return TradingAccountListResponse(
        items=accounts,
        total=len(accounts),
    )


# ============================================================
# CONNECT
# ============================================================

@router.get(
    "/active",
    response_model=TradingAccountResponse,
)
async def get_active_trading_account(
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Return the authenticated user's active connected trading account.
    """

    try:
        return await service.get_active_account(
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.post(
    "/{account_id}/connect",
    response_model=TradingAccountResponse,
)
async def connect_trading_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
    bridge_service: MT5BridgeService = Depends(get_mt5_bridge_service),
):
    """
    Connect an owned trading account to the MT5 bridge
    and synchronize its broker state into AQE.

    The broker password is retrieved from encrypted storage,
    decrypted only in memory, and sent to the MT5 bridge.

    The password is never returned to the frontend.
    """

    # ========================================================
    # 1. Verify account ownership
    # ========================================================

    try:
        account = await service.get_owned_account(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # ========================================================
    # 2. Retrieve and decrypt broker credentials
    # ========================================================

    try:
        password = await service.get_decrypted_credentials(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # ========================================================
    # 3. Connect selected account through MT5 bridge
    # ========================================================

    try:
        bridge_status = await bridge_service.connect(
            login=account.login,
            password=password,
            server=account.server,
        )

    except MT5BridgeError as exc:

        try:
            await service.update_account_state(
                account_id=account.id,
                state=TradingAccountStateUpdate(
                    status=AccountStatus.ERROR,
                ),
            )
        except ValueError:
            pass

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    # ========================================================
    # 4. Verify bridge reported successful connection
    # ========================================================

    if not bridge_status.get("connected", False):

        try:
            await service.update_account_state(
                account_id=account.id,
                state=TradingAccountStateUpdate(
                    status=AccountStatus.ERROR,
                ),
            )
        except ValueError:
            pass

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MT5 bridge failed to establish the connection.",
        )

    # ========================================================
    # 5. Verify connected account login
    # ========================================================

    bridge_login = bridge_status.get("login")

    if bridge_login is not None:

        try:
            bridge_login = int(bridge_login)

        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MT5 bridge returned an invalid account login.",
            ) from exc

        if bridge_login != account.login:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=("MT5 bridge connected to an unexpected " "trading account."),
            )

    # ========================================================
    # 6. Verify connected trading server
    # ========================================================

    bridge_server = bridge_status.get("server")

    if bridge_server is not None and bridge_server != account.server:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("MT5 bridge connected to an unexpected " "trading server."),
        )

    # ========================================================
    # 7. Retrieve actual MT5 account state
    # ========================================================

    try:
        broker_account = await bridge_service.get_account()

    except MT5BridgeError as exc:

        try:
            await service.update_account_state(
                account_id=account.id,
                state=TradingAccountStateUpdate(
                    status=AccountStatus.ERROR,
                ),
            )
        except ValueError:
            pass

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "MT5 account connected, but account state "
                f"could not be retrieved: {exc}"
            ),
        ) from exc

    # ========================================================
    # 8. Verify account identity from /account
    # ========================================================

    broker_login = broker_account.get("login")

    if broker_login is not None:

        try:
            broker_login = int(broker_login)

        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MT5 bridge returned an invalid account login.",
            ) from exc

        if broker_login != account.login:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "MT5 account information belongs to a " "different trading account."
                ),
            )

    broker_server = broker_account.get("server")

    if broker_server is not None and broker_server != account.server:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "MT5 account information belongs to a " "different trading server."
            ),
        )

    # ========================================================
    # 9. Map MT5 state → AQE state
    # ========================================================

    state = TradingAccountStateUpdate(
        status=AccountStatus.CONNECTED,
        currency=broker_account.get("currency"),
        leverage=broker_account.get("leverage"),
        balance=broker_account.get("balance"),
        equity=broker_account.get("equity"),
        margin=broker_account.get("margin"),
        free_margin=broker_account.get("margin_free"),
        margin_level=broker_account.get("margin_level"),
    )

    # ========================================================
    # 10. Persist synchronized state
    # ========================================================

    try:
        account = await service.update_account_state(
            account_id=account.id,
            state=state,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return account


# ============================================================
# DISCONNECT
# ============================================================


@router.post(
    "/{account_id}/disconnect",
    response_model=TradingAccountResponse,
)
async def disconnect_trading_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
    bridge_service: MT5BridgeService = Depends(get_mt5_bridge_service),
):
    """
    Disconnect the selected trading account from the MT5 bridge.

    Because the current MT5 bridge maintains one global MT5 session,
    the bridge connection is verified before disconnecting it.
    """

    # ========================================================
    # 1. Verify account ownership
    # ========================================================

    try:
        account = await service.get_owned_account(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # ========================================================
    # 2. Get current bridge status
    # ========================================================

    try:
        bridge_status = await bridge_service.status()

    except MT5BridgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("Unable to determine MT5 bridge " f"connection status: {exc}"),
        ) from exc

    connected = bridge_status.get("connected", False)

    # ========================================================
    # 3. Bridge already disconnected
    # ========================================================

    if not connected:

        try:
            return await service.update_account_state(
                account_id=account.id,
                state=TradingAccountStateUpdate(
                    status=AccountStatus.DISCONNECTED,
                ),
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    # ========================================================
    # 4. Verify active bridge login
    # ========================================================

    bridge_login = bridge_status.get("login")

    if bridge_login is not None:

        try:
            bridge_login = int(bridge_login)

        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MT5 bridge returned an invalid account login.",
            ) from exc

        if bridge_login != account.login:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The MT5 bridge is currently connected to a "
                    "different trading account. Disconnecting this "
                    "account was refused."
                ),
            )

    # ========================================================
    # 5. Verify active bridge server
    # ========================================================

    bridge_server = bridge_status.get("server")

    if bridge_server is not None and bridge_server != account.server:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The MT5 bridge is currently connected to a "
                "different trading server. Disconnecting this "
                "account was refused."
            ),
        )

    # ========================================================
    # 6. Disconnect MT5
    # ========================================================

    try:
        await bridge_service.disconnect()

    except MT5BridgeError as exc:

        try:
            await service.update_account_state(
                account_id=account.id,
                state=TradingAccountStateUpdate(
                    status=AccountStatus.ERROR,
                ),
            )
        except ValueError:
            pass

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to disconnect the MT5 account: {exc}",
        ) from exc

    # ========================================================
    # 7. Synchronize AQE state
    # ========================================================

    try:
        account = await service.update_account_state(
            account_id=account.id,
            state=TradingAccountStateUpdate(
                status=AccountStatus.DISCONNECTED,
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return account


# ============================================================
# ACTIVE / INACTIVE
# ============================================================


@router.patch(
    "/{account_id}/active",
    response_model=TradingAccountResponse,
)
async def set_trading_account_active(
    account_id: UUID,
    active: bool,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Enable or disable a trading account in AQE.

    This does not connect or disconnect MT5.
    """

    try:
        return await service.set_active(
            account_id=account_id,
            user_id=current_user.id,
            active=active,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ============================================================
# GET ONE
# ============================================================


@router.get(
    "/{account_id}",
    response_model=TradingAccountResponse,
)
async def get_trading_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Retrieve a specific trading account owned by the
    authenticated user.
    """

    try:
        return await service.get_owned_account(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ============================================================
# UPDATE
# ============================================================


@router.patch(
    "/{account_id}",
    response_model=TradingAccountResponse,
)
async def update_trading_account(
    account_id: UUID,
    data: TradingAccountUpdate,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Update configuration for a trading account.

    Broker passwords are encrypted before being persisted.

    Broker-derived financial state is intentionally excluded
    from this endpoint.
    """

    try:
        return await service.update_account(
            account_id=account_id,
            user_id=current_user.id,
            data=data,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ============================================================
# DELETE
# ============================================================


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_trading_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(get_trading_account_service),
):
    """
    Delete a trading account owned by the authenticated user.
    """

    try:
        await service.delete_account(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.post(
    "/{account_id}/symbols/sync",
)
async def sync_trading_account_symbols(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TradingAccountService = Depends(
        get_trading_account_service
    ),
    bridge_service: MT5BridgeService = Depends(
        get_mt5_bridge_service
    ),
    sync_service: SymbolSyncService = Depends(
        get_symbol_sync_service
    ),
):
    """
    Synchronize the symbols exposed by the connected MT5 account
    into AQE.
    """

    try:
        account = await service.get_owned_account(
            account_id=account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if account.status != AccountStatus.CONNECTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Trading account must be connected before "
                "symbols can be synchronized."
            ),
        )

    try:
        bridge_status = await bridge_service.status()

    except MT5BridgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to determine MT5 bridge "
                f"connection status: {exc}"
            ),
        ) from exc

    if not bridge_status.get("connected", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Trading account is marked as connected, "
                "but the MT5 bridge is not connected."
            ),
        )

    bridge_login = bridge_status.get("login")

    if bridge_login is not None:

        try:
            bridge_login = int(bridge_login)

        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MT5 bridge returned an invalid account login.",
            ) from exc

        if bridge_login != account.login:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The MT5 bridge is connected to a "
                    "different trading account."
                ),
            )

    bridge_server = bridge_status.get("server")

    if (
        bridge_server is not None
        and bridge_server != account.server
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The MT5 bridge is connected to a "
                "different trading server."
            ),
        )

    try:
        return await sync_service.sync_account_symbols(
            account_id=account.id,
            user_id=current_user.id,
        )

    except SymbolSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc