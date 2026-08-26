import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_broker_manager, get_db
from app.core.security import verify_token
from app.repositories.user_repository import UserRepository


router = APIRouter(prefix="/stream", tags=["stream"])


@router.websocket("/ticks/{symbol}")
async def stream_ticks(
    websocket: WebSocket,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream broker ticks over an authenticated WebSocket connection."""
    token = websocket.query_params.get("token")
    try:
        if token is None:
            raise ValueError("Missing access token")
        payload = verify_token(token, expected_type="access")
        user = await UserRepository(db).get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise ValueError("Invalid user")
    except ValueError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    broker = get_broker_manager()
    interval = 0.25

    try:
        while True:
            tick = await broker.get_tick(symbol)
            await websocket.send_json({"symbol": symbol, "tick": tick})
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    finally:
        with suppress(Exception):
            await websocket.close()