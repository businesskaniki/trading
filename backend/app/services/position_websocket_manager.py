
from __future__ import annotations

import asyncio
import logging

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.database.session import SessionLocal
from app.repositories.position_repository import PositionRepository
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.schemas.position import PositionResponse
from app.services.position_service import PositionService

logger = logging.getLogger(__name__)


class PositionWebSocketManager:
    """
    Manage authenticated position WebSocket clients.

    One background feed is maintained per user within this application
    process. Feeds start on demand and stop when the user's final
    WebSocket connection disconnects.

    PositionReconciliationService owns broker synchronization and
    persistence. This manager only reads the persisted AQE position
    ledger and broadcasts snapshots to connected clients.

    This service must never independently retrieve positions from MT5.
    """

    POLL_INTERVAL_SECONDS = 2.0
    ERROR_RETRY_SECONDS = 3.0

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._feed_tasks: dict[UUID, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    # ==========================================================
    # CONNECTION LIFECYCLE
    # ==========================================================

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

            client_count = len(connections)

        logger.info(
            "Position WebSocket connected. user_id=%s clients=%s",
            user_id,
            client_count,
        )

    async def disconnect(
        self,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        """Unregister a socket and stop its feed if it is no longer used."""

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

    async def _has_connections(
        self,
        user_id: UUID,
    ) -> bool:
        """Return whether the user still has active WebSocket clients."""

        async with self._lock:
            return bool(self._connections.get(user_id))

    async def _get_connections(
        self,
        user_id: UUID,
    ) -> list[WebSocket]:
        """Return a snapshot of the user's connected WebSockets."""

        async with self._lock:
            return list(self._connections.get(user_id, set()))

    # ==========================================================
    # BROADCAST
    # ==========================================================

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
            *(
                websocket.send_json(message)
                for websocket in connections
            ),
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

    # ==========================================================
    # PERSISTED POSITION SNAPSHOT
    # ==========================================================

    async def _fetch_snapshot(
        self,
        user_id: UUID,
        account_id: UUID,
        sync_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Read the latest persisted AQE positions for an account.

        IMPORTANT:

        This method does not retrieve positions from the broker.

        PositionReconciliationService is the sole owner of periodic
        broker-position synchronization and position persistence.

        A fresh database session is used for each snapshot.
        Both user_id and account_id are explicitly applied when
        retrieving positions to prevent cross-account data leakage.
        """

        async with SessionLocal() as db:
            position_repository = PositionRepository(db)
            account_repository = TradingAccountRepository(db)

            position_service = PositionService(
                repository=position_repository,
                account_repository=account_repository,
            )

            positions = await position_service.get_open_positions_for_user(
                user_id=user_id,
                account_id=account_id,
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

    # ==========================================================
    # USER FEED
    # ==========================================================

    async def _run_user_feed(
        self,
        user_id: UUID,
    ) -> None:
        """
        Broadcast persisted positions for the active AQE runtime.

        The active runtime determines the account scope.

        PositionReconciliationService maintains the persisted position
        ledger. This feed only reads that ledger and broadcasts it.

        Never fall back to a generic broker factory or independently
        retrieve positions from MT5.
        """

        current_task = asyncio.current_task()
        last_error: str | None = None

        try:
            # Local import avoids a module-level dependency cycle.
            from app.core.engine import get_aqe_engine

            while await self._has_connections(user_id):
                try:
                    engine = get_aqe_engine()

                    engine_status = getattr(
                        engine.context.status,
                        "value",
                        str(engine.context.status),
                    )

                    if str(engine_status).upper() != "RUNNING":
                        raise RuntimeError(
                            "AQE engine must be RUNNING to broadcast live positions."
                        )

                    runtime = engine.runtime

                    if runtime is None:
                        raise RuntimeError(
                            "AQE engine is RUNNING but has no active execution runtime."
                        )

                    runtime_account = runtime.account

                    # --------------------------------------------------
                    # Validate runtime ownership.
                    # --------------------------------------------------

                    try:
                        runtime_user_id = UUID(
                            str(runtime_account.user_id),
                        )
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise PermissionError(
                            "The active runtime account has no valid owner."
                        ) from exc

                    if runtime_user_id != user_id:
                        raise PermissionError(
                            "The active AQE runtime is not owned by this user."
                        )

                    account_id = runtime_account.account_id

                    # --------------------------------------------------
                    # Read the reconciliation service's latest result.
                    # --------------------------------------------------

                    reconciliation = getattr(
                        runtime,
                        "position_reconciliation_service",
                        None,
                    )

                    if reconciliation is None:
                        raise RuntimeError(
                            "Position reconciliation service is not configured."
                        )

                    if not reconciliation.running:
                        raise RuntimeError(
                            "Position reconciliation is not running. "
                            "Cannot guarantee fresh persisted positions."
                        )

                    sync_result = reconciliation.last_result

                    # --------------------------------------------------
                    # Read persisted AQE positions.
                    #
                    # No broker calls occur in this operation.
                    # --------------------------------------------------

                    snapshot = await self._fetch_snapshot(
                        user_id=user_id,
                        account_id=account_id,
                        sync_result=sync_result,
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
                    error_message = (
                        f"Unable to publish persisted position snapshot: {exc}"
                    )

                    # Avoid flooding logs and the WebSocket with the
                    # same recurring error on every polling cycle.
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
            # Only remove the task if this feed still owns the registry
            # entry. Do not accidentally remove a replacement task.
            async with self._lock:
                if self._feed_tasks.get(user_id) is current_task:
                    self._feed_tasks.pop(user_id, None)


position_websocket_manager = PositionWebSocketManager()
