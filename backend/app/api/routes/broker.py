from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_trading_account_service,
)
from app.core.constants import BrokerType
from app.services.mt5_bridge_service import (
    MT5BridgeError,
    MT5BridgeService,
)
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
):
    """Return broker data only when the MT5 identity matches the owned account."""

    try:
        account = await account_service.get_owned_account(
            account_id,
            current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    broker_type = getattr(account.broker, "value", account.broker)
    if str(broker_type).upper() != BrokerType.MT5.value:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Broker account data is not supported for broker {broker_type}.",
        )

    # Respect an account-specific bridge URL without changing the global runtime.
    bridge_service = MT5BridgeService(bridge_url=account.bridge_url)

    try:
        connection = await bridge_service.status()

        if connection.get("connected") is not True:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="MT5 bridge is not connected. Connect the requested trading account first.",
            )

        def validate_identity(payload: dict, source: str) -> None:
            login = payload.get("login")
            server = payload.get("server")

            if login is None or server is None:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"MT5 bridge {source} response is missing login or server identity.",
                )

            try:
                login = int(login)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"MT5 bridge {source} response contains an invalid login.",
                ) from exc

            if login != account.login or str(server).strip() != account.server.strip():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"MT5 bridge {source} belongs to a different account or server. "
                        "No account data was returned."
                    ),
                )

        validate_identity(connection, "connection status")

        broker_account = await bridge_service.get_account()
        validate_identity(broker_account, "account")

        return broker_account

    except MT5BridgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
