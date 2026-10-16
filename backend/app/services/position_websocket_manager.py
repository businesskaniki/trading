from __future__ import annotations

import asyncio
import logging

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.database.session import SessionLocal
from app.repositories.order_repository import OrderRepository
from app.repositories.position_repository import PositionRepository
from app.repositories.trade_repository import TradeRepository
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.schemas.position import PositionResponse
from app.services.execution_service import ExecutionService
from app.services.position_service import PositionService
from app.services.position_sync_service import PositionSyncService
from app.services.trade_service import TradeService

logger = logging.getLogger(__name__)


class PositionWebSocketManager:
    """
    Manage authenticated position WebSocket clients.

    A single background feed is maintained per user within this
    application process. Feeds start on demand and stop when the
    user's final WebSocket connection disconnects.

    The MT5 bridge currently supplies REST snapshots, so the backend
    refreshes broker state periodically and broadcasts the results.
    """

    POLL_INTERVAL_SECONDS = 1.0
    ERROR_RETRY_SECONDS = 3.0

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._feed_tasks: dict[UUID, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        """Register a previously accepted and authenticated socket."""

        async with self._lock:
            connections = self._connections.setdefault(
                user_id,
                set(),
            )
            connections.add(websocket)

            task = self._feed_tasks.get(user_id)

            if task is None or task.done():
                self._feed_tasks[user_id] = asyncio.create_task(
                    self._run_user_feed(user_id),
                    name=f"position-feed-{user_id}",
                )

        logger.info(
            "Position WebSocket connected. user_id=%s clients=%s",
            user_id,
            len(self._connections.get(user_id, set())),
        )

    async def disconnect(
        self,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        """Unregister a socket and stop its user's feed if unused."""

        task_to_cancel = None

        async with self._lock:
            connections = self._connections.get(user_id)

            if connections is not None:
                connections.discard(websocket)

                if not connections:
                    self._connections.pop(user_id, None)
                    task_to_cancel = self._feed_tasks.pop(
                        user_id,
                        None,
                    )

        current_task = asyncio.current_task()

        if (
            task_to_cancel is not None
            and task_to_cancel is not current_task
            and not task_to_cancel.done()
        ):
            task_to_cancel.cancel()

            await asyncio.gather(
                task_to_cancel,
                return_exceptions=True,
            )

        logger.info(
            "Position WebSocket disconnected. user_id=%s",
            user_id,
        )

    async def _has_connections(self, user_id: UUID) -> bool:
        async with self._lock:
            return bool(self._connections.get(user_id))

    async def _get_connections(
        self,
        user_id: UUID,
    ) -> list[WebSocket]:
        async with self._lock:
            return list(self._connections.get(user_id, set()))

    async def _broadcast(
        self,
        user_id: UUID,
        message: dict[str, Any],
    ) -> None:
        """Push a message to every active socket for the user."""

        connections = await self._get_connections(user_id)

        if not connections:
            return

        results = await asyncio.gather(
            *(websocket.send_json(message) for websocket in connections),
            return_exceptions=True,
        )

        stale_connections = [
            websocket
            for websocket, result in zip(connections, results)
            if isinstance(result, BaseException)
        ]

        if stale_connections:
            async with self._lock:
                active = self._connections.get(user_id)

                if active is not None:
                    for websocket in stale_connections:
                        active.discard(websocket)

                    if not active:
                        self._connections.pop(user_id, None)

    async def _fetch_snapshot(
        self,
        user_id: UUID,
        broker,
    ) -> dict[str, Any]:
        """
        Use a short-lived DB session for each synchronization cycle.

        Never retain an AsyncSession for the lifetime of a WebSocket.
        """

        async with SessionLocal() as db:
            position_repository = PositionRepository(db)
            account_repository = TradingAccountRepository(db)
            order_repository = OrderRepository(db)

            position_service = PositionService(
                repository=position_repository,
                account_repository=account_repository,
            )

            trade_service = TradeService(
                repository=TradeRepository(db),
                position_repository=position_repository,
            )

            execution_service = ExecutionService(
                broker=broker,
            )

            sync_service = PositionSyncService(
                execution_service=execution_service,
                position_repository=position_repository,
                position_service=position_service,
                order_repository=order_repository,
                trade_service=trade_service,
            )

            # Refresh the database from the broker's current state.
            sync_result = await sync_service.sync_positions(
                user_id=user_id,
            )

            # Read the updated records within the same session.
            positions = await position_service.get_positions(
                user_id=user_id,
            )

            serialized_positions = [
                PositionResponse.model_validate(position).model_dump(
                    mode="json",
                )
                for position in positions
            ]

            return {
                "type": "positions.snapshot",
                "timestamp": datetime.now(
                    timezone.utc,
                ).isoformat(),
                "positions": serialized_positions,
                "sync": sync_result,
            }

    async def _run_user_feed(
        self,
        user_id: UUID,
    ) -> None:
        """
        Refresh broker state while the user has active subscribers.
        """

        current_task = asyncio.current_task()
        last_error: str | None = None

        try:
            # Import locally to avoid a module-level dependency cycle:
            # the API dependency module also imports PositionSyncService.
            from app.api.dependencies import get_broker_manager

            broker = get_broker_manager()

            while await self._has_connections(user_id):
                try:
                    snapshot = await self._fetch_snapshot(
                        user_id=user_id,
                        broker=broker,
                    )

                    await self._broadcast(
                        user_id,
                        snapshot,
                    )

                    last_error = None
                    delay = self.POLL_INTERVAL_SECONDS

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    error_message = "Unable to refresh broker positions: " f"{exc}"

                    if error_message != last_error:
                        logger.exception(
                            "Position feed failed. user_id=%s",
                            user_id,
                        )

                        await self._broadcast(
                            user_id,
                            {
                                "type": "positions.error",
                                "message": error_message,
                                "timestamp": datetime.now(
                                    timezone.utc,
                                ).isoformat(),
                            },
                        )

                        last_error = error_message

                    delay = self.ERROR_RETRY_SECONDS

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Position feed terminated. user_id=%s",
                user_id,
            )

        finally:
            async with self._lock:
                if self._feed_tasks.get(user_id) is current_task:
                    self._feed_tasks.pop(user_id, None)


position_websocket_manager = PositionWebSocketManager()
