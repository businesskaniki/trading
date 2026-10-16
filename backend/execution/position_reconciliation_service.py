from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.database.session import SessionLocal
from app.repositories.order_repository import OrderRepository
from app.repositories.position_repository import PositionRepository
from app.services.execution_service import ExecutionService
from app.services.position_service import PositionService
from app.services.position_sync_service import PositionSyncService
from app.services.trade_service import TradeService
from app.repositories.trade_repository import TradeRepository

logger = logging.getLogger(__name__)


class PositionReconciliationError(Exception):
    """Base exception for position reconciliation failures."""


class PositionReconciliationService:
    """
    Continuously reconcile the active broker's open positions with AQE.

    The service is account-scoped.

    Lifecycle:

        AQEEngine.start()
            ↓
        broker connected
            ↓
        immediate position synchronization
            ↓
        background synchronization loop
            ↓
        AQE Position records stay aligned with broker state

    This service does not:

        - place orders;
        - modify broker positions;
        - close broker positions;
        - calculate risk;
        - manage strategies.

    It only reads authoritative broker position state and synchronizes
    AQE's persisted position/trade ledger.
    """

    DEFAULT_INTERVAL_SECONDS = 2.0

    def __init__(
        self,
        *,
        broker: BrokerManager,
        account_id: UUID,
        user_id: UUID,
        session_factory=SessionLocal,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        if not isinstance(account_id, UUID):
            raise TypeError("account_id must be a UUID.")

        if not isinstance(user_id, UUID):
            raise TypeError("user_id must be a UUID.")

        if not callable(session_factory):
            raise TypeError("session_factory must be callable.")

        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero.")

        self._broker = broker
        self._account_id = account_id
        self._user_id = user_id
        self._session_factory = session_factory
        self._interval_seconds = float(interval_seconds)

        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._reconcile_lock = asyncio.Lock()

        self._last_result: dict[str, Any] | None = None

    # ==================================================================
    # STATE
    # ==================================================================

    @property
    def running(self) -> bool:
        """Return whether position reconciliation is running."""

        return self._running

    @property
    def account_id(self) -> UUID:
        """Return the account being reconciled."""

        return self._account_id

    @property
    def last_result(self) -> dict[str, Any] | None:
        """Return the most recent synchronization result."""

        if self._last_result is None:
            return None

        return dict(self._last_result)

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(self) -> None:
        """
        Perform an immediate synchronization and start the background loop.

        The broker is expected to already be connected.
        """

        if self._running:
            return

        logger.info(
            "Starting position reconciliation. " "account_id=%s interval=%ss",
            self._account_id,
            self._interval_seconds,
        )

        # --------------------------------------------------------------
        # Initial synchronization is deliberately synchronous.
        #
        # The engine must know the current broker position state before
        # strategy execution begins.
        # --------------------------------------------------------------

        try:
            result = await self._reconcile_once()

        except Exception as exc:
            logger.exception(
                "Initial position reconciliation failed. " "account_id=%s",
                self._account_id,
            )

            raise PositionReconciliationError(
                "Initial position reconciliation failed for account "
                f"{self._account_id}: {exc}"
            ) from exc

        self._last_result = result

        self._running = True

        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"aqe-position-reconciliation-{self._account_id}",
        )

        logger.info(
            "Position reconciliation started. " "account_id=%s result=%s",
            self._account_id,
            result,
        )

    async def stop(self) -> None:
        """Stop the background reconciliation loop."""

        if not self._running and self._task is None:
            return

        logger.info(
            "Stopping position reconciliation. account_id=%s",
            self._account_id,
        )

        self._running = False

        task = self._task
        self._task = None

        if task is not None:
            task.cancel()

            try:
                await task

            except asyncio.CancelledError:
                pass

            except Exception:
                logger.exception(
                    "Position reconciliation loop failed during shutdown. "
                    "account_id=%s",
                    self._account_id,
                )

        logger.info(
            "Position reconciliation stopped. account_id=%s",
            self._account_id,
        )

    # ==================================================================
    # RECONCILIATION
    # ==================================================================

    async def _reconcile_once(self) -> dict[str, Any]:
        """
        Execute one complete broker → AQE position synchronization cycle.
        """

        async with self._reconcile_lock:
            async with self._session_factory() as db:
                position_repository = PositionRepository(db)
                order_repository = OrderRepository(db)

                position_service = PositionService(
                    position_repository,
                )

                trade_service = TradeService(
                    repository=TradeRepository(db),
                    position_repository=position_repository,
                )

                execution_service = ExecutionService(
                    broker=self._broker,
                    account_id=self._account_id,
                )

                synchronizer = PositionSyncService(
                    execution_service=execution_service,
                    position_repository=position_repository,
                    position_service=position_service,
                    order_repository=order_repository,
                    trade_service=trade_service,
                )

                result = await synchronizer.sync_positions(
                    user_id=self._user_id,
                )

                return result

    async def _run_loop(self) -> None:
        """Run periodic position reconciliation."""

        while self._running:
            try:
                await asyncio.sleep(
                    self._interval_seconds,
                )

                if not self._running:
                    break

                try:
                    result = await self._reconcile_once()

                    self._last_result = result

                    logger.debug(
                        "Position reconciliation completed. " "account_id=%s result=%s",
                        self._account_id,
                        result,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "Position reconciliation cycle failed. " "account_id=%s",
                        self._account_id,
                    )

            except asyncio.CancelledError:
                break

            except Exception:
                logger.exception(
                    "Unexpected position reconciliation loop failure. " "account_id=%s",
                    self._account_id,
                )

                if self._running:
                    await asyncio.sleep(1.0)

        logger.debug(
            "Position reconciliation loop exited. account_id=%s",
            self._account_id,
        )


__all__ = [
    "PositionReconciliationError",
    "PositionReconciliationService",
]
