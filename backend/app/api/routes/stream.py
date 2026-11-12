from contextlib import suppress
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.security import verify_token
from app.market_data.live import live_tick_hub
from app.market_data.service import market_data_service
from app.repositories.account_symbol_repository import AccountSymbolRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.repositories.user_repository import UserRepository
from app.tasks.market_data import record_market_history

router = APIRouter(prefix="/stream", tags=["stream"])


@router.websocket("/ticks/{account_id}/{symbol_id}")
async def stream_ticks(
    websocket: WebSocket,
    account_id: UUID,
    symbol_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stream canonical market ticks for an authenticated account position."""

    # --------------------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------------------

    protocol = websocket.headers.get("sec-websocket-protocol", "")
    token = protocol.removeprefix("bearer.") if protocol.startswith("bearer.") else None

    try:
        if token is None:
            raise ValueError("Missing access token")

        payload = verify_token(token, expected_type="access")
        user = await UserRepository(db).get_by_id(payload["sub"])

        if not user or not user.is_active or payload.get("ver") != user.token_version:
            raise ValueError("Invalid user")

    except (ValueError, KeyError, TypeError):
        await websocket.close(code=1008)
        return

    # --------------------------------------------------------------
    # ACCOUNT OWNERSHIP
    # --------------------------------------------------------------

    account = await TradingAccountRepository(db).get_by_id_and_user(
        account_id=account_id,
        user_id=user.id,
    )

    if account is None or not account.active:
        await websocket.close(code=1008)
        return

    # --------------------------------------------------------------
    # ACCOUNT SYMBOL RESOLUTION
    # --------------------------------------------------------------

    account_symbol = await AccountSymbolRepository(db).get_by_account_and_symbol(
        account_id=account_id,
        symbol_id=symbol_id,
    )

    if (
        account_symbol is None
        or account_symbol.symbol is None
        or not isinstance(account_symbol.broker_symbol, str)
        or not account_symbol.broker_symbol.strip()
        or not isinstance(account_symbol.symbol.name, str)
        or not account_symbol.symbol.name.strip()
    ):
        await websocket.close(code=1008)
        return

    broker_symbol = account_symbol.broker_symbol.strip()
    canonical_symbol = account_symbol.symbol.name.strip()

    # --------------------------------------------------------------
    # VERIFY THE CONNECTED MT5 ACCOUNT
    # --------------------------------------------------------------

    try:
        bridge_status = await market_data_service.bridge.status()
    except Exception:
        await websocket.close(code=1011)
        return

    if not bridge_status.get("connected", False):
        await websocket.close(code=1013)
        return

    try:
        bridge_login = int(bridge_status.get("login"))
        account_login = int(account.login)
    except (TypeError, ValueError):
        await websocket.close(code=1011)
        return

    bridge_server = bridge_status.get("server")

    if (
        bridge_login != account_login
        or not isinstance(bridge_server, str)
        or bridge_server.strip() != str(account.server).strip()
    ):
        await websocket.close(code=1008)
        return

    # --------------------------------------------------------------
    # SUBSCRIBE USING THE TWO DISTINCT SYMBOL IDENTITIES
    # --------------------------------------------------------------

    await websocket.accept(subprotocol=protocol)

    try:
        # MT5 requires the exact broker-specific symbol.
        await market_data_service.subscribe(broker_symbol)

        # History is requested from MT5 using the broker symbol but
        # normalized and stored under AQE's canonical symbol.
        record_market_history.delay(
            broker_symbol,
            canonical_symbol=canonical_symbol,
        )

    except Exception:
        await websocket.close(code=1011)
        return

    # Redis consumer publishes ticks using canonical symbols.
    queue = live_tick_hub.subscribe(canonical_symbol)

    try:
        while True:
            tick = await queue.get()

            await websocket.send_json(
                {
                    "symbol": canonical_symbol,
                    "tick": asdict(tick),
                }
            )

    except WebSocketDisconnect:
        return

    finally:
        live_tick_hub.unsubscribe(canonical_symbol, queue)

        with suppress(Exception):
            await websocket.close()
