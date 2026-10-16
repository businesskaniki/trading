from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.routes.trading_accounts import get_trading_account_service
from app.core.config import settings
from app.services.trading_account_service import TradingAccountService

router = APIRouter(
    prefix="/internal/bridge",
    tags=["Internal Bridge"],
)


class MT5CredentialLookupRequest(BaseModel):
    login: int = Field(gt=0)
    server: str = Field(min_length=1, max_length=128)


@router.post("/mt5-credentials")
async def recover_mt5_credentials(
    data: MT5CredentialLookupRequest,
    x_bridge_token: str | None = Header(
        default=None,
        alias="X-Bridge-Token",
    ),
    service: TradingAccountService = Depends(get_trading_account_service),
) -> dict[str, int | str]:
    """
    Internal bridge-only endpoint.

    The shared bridge token is required before any database lookup or
    credential decryption. Never call this endpoint from the frontend.
    """
    configured_token = settings.BRIDGE_API_KEY

    if (
        not configured_token
        or not x_bridge_token
        or not hmac.compare_digest(
            x_bridge_token,
            configured_token,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bridge credentials.",
        )

    try:
        return await service.get_mt5_credentials_for_bridge(
            login=data.login,
            server=data.server,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
