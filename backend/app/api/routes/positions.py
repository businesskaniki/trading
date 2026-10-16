from __future__ import annotations

import asyncio
import logging

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_current_user,
    get_position_service,
    get_position_sync_service,
)
from app.core.constants import PositionStatus
from app.core.security import verify_token
from app.database.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.schemas.position import (
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)
from app.services.position_service import PositionService
from app.services.position_sync_service import PositionSyncService
from app.services.position_websocket_manager import (
    position_websocket_manager,
)

logger = logging.getLogger(__name__)


# ==========================================================
# RESPONSE SCHEMAS
# ==========================================================


class PositionSyncResponse(BaseModel):
    """Summary returned after synchronizing broker positions into AQE."""

    broker_positions: int = Field(ge=0)
    created: int = Field(ge=0)
    updated: int = Field(ge=0)
    closed: int = Field(ge=0)
    ignored: int = Field(ge=0)


# ==========================================================
# ROUTER
# ==========================================================

# Do not place get_current_user in router-wide dependencies.
# WebSocket authentication is handled explicitly below.
# Every HTTP endpoint declares its own authentication dependency.

router = APIRouter(
    prefix="/positions",
    tags=["positions"],
)


# ==========================================================
# CREATE POSITION
# ==========================================================


@router.post(
    "/",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_position(
    payload: PositionCreate,
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.create_position(
            payload,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# LIST POSITIONS
# ==========================================================


@router.get(
    "/",
    response_model=list[PositionResponse],
)
async def list_positions(
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    """
    Return persisted positions for the authenticated user.

    Live updates are handled by the WebSocket feed. This endpoint
    remains a read-only REST endpoint for initial loading and fallback.
    """

    return await service.get_positions(
        user_id=current_user.id,
    )


# ==========================================================
# GET ONE POSITION
# ==========================================================


@router.get(
    "/{position_id}",
    response_model=PositionResponse,
)
async def get_position(
    position_id: UUID,
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.get_position(
            position_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# UPDATE POSITION
# ==========================================================


@router.patch(
    "/{position_id}",
    response_model=PositionResponse,
)
async def update_position(
    position_id: UUID,
    payload: PositionUpdate,
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.update_position(
            position_id,
            payload,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# UPDATE POSITION STATUS
# ==========================================================


@router.patch(
    "/{position_id}/status",
    response_model=PositionResponse,
)
async def update_position_status(
    position_id: UUID,
    status_value: PositionStatus,
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.update_position_status(
            position_id,
            status_value,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# DELETE POSITION
# ==========================================================


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_position(
    position_id: UUID,
    current_user=Depends(get_current_user),
    service: PositionService = Depends(get_position_service),
):
    try:
        await service.delete_position(
            position_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if message == "Position not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

    return None


# ==========================================================
# MANUAL BROKER POSITION SYNC
# ==========================================================


@router.post(
    "/sync",
    response_model=PositionSyncResponse,
)
async def sync_positions(
    current_user=Depends(get_current_user),
    service: PositionSyncService = Depends(
        get_position_sync_service,
    ),
):
    """
    Manually synchronize positions from the connected broker.
    """

    try:
        return await service.sync_positions(
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# AUTHENTICATED LIVE POSITION WEBSOCKET
# ==========================================================


@router.websocket("/ws")
async def positions_websocket(websocket: WebSocket):
    """
    Stream live position snapshots to an authenticated frontend client.

    Connection:
        ws://localhost:8000/api/v1/positions/ws

    First client message:
        {
            "type": "auth",
            "token": "<access-token>"
        }

    Server messages:
        authenticated
        positions.snapshot
        positions.error

    The position WebSocket manager owns the live feed lifecycle.
    """

    await websocket.accept()

    user_id: UUID | None = None
    registered = False

    try:
        # ------------------------------------------------------
        # 1. Authenticate the WebSocket connection
        # ------------------------------------------------------

        try:
            auth_message = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0,
            )

        except asyncio.TimeoutError:
            await websocket.close(
                code=4401,
                reason="Authentication timed out",
            )
            return

        except ValueError:
            await websocket.close(
                code=4401,
                reason="Invalid authentication message",
            )
            return

        if not isinstance(auth_message, dict):
            await websocket.close(
                code=4401,
                reason="Invalid authentication message",
            )
            return

        if auth_message.get("type") != "auth":
            await websocket.close(
                code=4401,
                reason="Authentication message required",
            )
            return

        token = auth_message.get("token")

        if not isinstance(token, str) or not token.strip():
            await websocket.close(
                code=4401,
                reason="Access token required",
            )
            return

        # ------------------------------------------------------
        # 2. Verify access token and retrieve active user
        # ------------------------------------------------------

        try:
            payload = verify_token(
                token,
                expected_type="access",
            )

            subject = payload.get("sub")

            if not subject:
                raise ValueError(
                    "Access token does not contain a subject",
                )

            async with SessionLocal() as db:
                user = await UserRepository(db).get_by_id(
                    subject,
                )

                if user is None or not user.is_active:
                    raise ValueError("Invalid or inactive user")

                user_id = user.id

        except (ValueError, TypeError, KeyError):
            await websocket.close(
                code=4401,
                reason="Authentication failed",
            )
            return

        # ------------------------------------------------------
        # 3. Confirm authentication to frontend
        # ------------------------------------------------------

        await websocket.send_json(
            {
                "type": "authenticated",
                "user_id": str(user_id),
            },
        )

        # ------------------------------------------------------
        # 4. Register client with position feed
        # ------------------------------------------------------

        await position_websocket_manager.connect(
            user_id=user_id,
            websocket=websocket,
        )

        registered = True

        logger.info(
            "Position WebSocket established for user %s",
            user_id,
        )

        # ------------------------------------------------------
        # 5. Keep connection alive
        # ------------------------------------------------------

        # The position manager sends snapshots independently.
        # This loop receives client messages and detects disconnects.
        while True:
            message = await websocket.receive_text()

            # Optional application-level ping.
            if message == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                    },
                )

    except WebSocketDisconnect:
        logger.info(
            "Position WebSocket disconnected for user %s",
            user_id,
        )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "Unexpected position WebSocket error for user %s",
            user_id,
        )

        try:
            await websocket.close(
                code=1011,
                reason="Position stream failed",
            )
        except Exception:
            pass

    finally:
        # Only unregister sockets that were successfully registered.
        if registered and user_id is not None:
            await position_websocket_manager.disconnect(
                user_id=user_id,
                websocket=websocket,
            )
