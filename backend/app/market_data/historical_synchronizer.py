from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.database.session import SessionLocal
from app.services.historical_data_service import HistoricalDataService
from app.services.mt5_bridge_service import MT5BridgeService

logger = logging.getLogger(__name__)


class HistoricalDataSynchronizer:
    """
    Keep historical market data synchronized for one account runtime.

    AccountSymbol.enabled is the authoritative selection for which
    symbols belonging to this account receive historical data.

    The synchronizer must use the account ID and bridge supplied by its
    runtime. It must never enumerate other database accounts or send
    their symbol mappings through this runtime's bridge.

    Historical candles are never deleted when a symbol is disabled.
    """

    def __init__(
        self,
        interval_seconds: int = 60,
        timeframe: str = "M15",
        count: int = 200,
        *,
        account_id: UUID,
        bridge_service: MT5BridgeService,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero.")

        if count <= 0:
            raise ValueError("count must be greater than zero.")

        self.interval_seconds = interval_seconds
        self.timeframe = timeframe
        self.count = count

        # This synchronizer belongs to one account runtime.
        self.account_id = account_id

        self._task: asyncio.Task | None = None
        self._running = False

        # Reuse the bridge configured for this runtime.
        self._bridge_service = bridge_service

        self._historical_data_service = HistoricalDataService(
            session_factory=SessionLocal,
            bridge_service=self._bridge_service,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the account-scoped historical-data synchronization loop."""

        if self._running:
            logger.warning(
                "Historical data synchronizer is already running. " "account_id=%s",
                self.account_id,
            )
            return

        self._running = True

        self._task = asyncio.create_task(
            self._run(),
            name=f"historical-data-synchronizer-{self.account_id}",
        )

        logger.info(
            "Historical data synchronizer started. "
            "account_id=%s interval=%ss timeframe=%s count=%s",
            self.account_id,
            self.interval_seconds,
            self.timeframe,
            self.count,
        )

    async def stop(self) -> None:
        """Stop the synchronization loop cleanly."""

        if not self._running and self._task is None:
            return

        self._running = False
        task = self._task
        self._task = None

        if task is not None:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info(
            "Historical data synchronizer stopped. account_id=%s",
            self.account_id,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Periodically synchronize enabled symbols for this account."""

        while self._running:
            try:
                await self._synchronize()

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Unexpected error in historical data synchronizer. "
                    "account_id=%s",
                    self.account_id,
                )

            if not self._running:
                break

            try:
                await asyncio.sleep(self.interval_seconds)

            except asyncio.CancelledError:
                raise

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------

    async def _synchronize(self) -> None:
        """
        Synchronize only enabled symbols belonging to this runtime account.

        HistoricalDataService applies the account_id filter when selecting
        AccountSymbol records. No other database account is enumerated here.
        """

        if not self._running:
            return

        logger.debug(
            "Starting historical-data synchronization. account_id=%s",
            self.account_id,
        )

        try:
            result = await self._historical_data_service.sync_selected_symbols(
                account_id=self.account_id,
                timeframe=self.timeframe,
                count=self.count,
            )

            logger.info(
                "Historical synchronization completed. "
                "account_id=%s selected=%s synchronized=%s failed=%s",
                self.account_id,
                result["symbols_selected"],
                result["symbols_synchronized"],
                result["symbols_failed"],
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Historical synchronization failed. account_id=%s",
                self.account_id,
            )
