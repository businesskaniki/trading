from contextlib import suppress
from dataclasses import asdict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.security import verify_token
from app.market_data.live import live_tick_hub
from app.market_data.service import market_data_service
from app.repositories.user_repository import UserRepository


router = APIRouter(prefix="/stream", tags=["stream"])


@router.websocket("/ticks/{symbol}")
async def stream_ticks(
    websocket: WebSocket,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream broker ticks over an authenticated WebSocket connection."""
    protocol = websocket.headers.get("sec-websocket-protocol", "")
    token = protocol.removeprefix("bearer.") if protocol.startswith("bearer.") else None
    try:
        if token is None:
            raise ValueError("Missing access token")
        payload = verify_token(token, expected_type="access")
        user = await UserRepository(db).get_by_id(payload["sub"])
        if not user or not user.is_active or payload.get("ver") != user.token_version:
            raise ValueError("Invalid user")
    except ValueError:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=protocol)
    try:
        await market_data_service.subscribe(symbol)
        # Keep durable history warm independently of the live socket.
        from app.tasks.market_data import record_market_history
        record_market_history.delay(symbol)
    except Exception:
        await websocket.close(code=1011)
        return
    queue = live_tick_hub.subscribe(symbol)

    try:
        while True:
            tick = await queue.get()
            await websocket.send_json({"symbol": symbol, "tick": asdict(tick)})
    except WebSocketDisconnect:
        return
    finally:
        live_tick_hub.unsubscribe(symbol, queue)
        with suppress(Exception):
            await websocket.close()
