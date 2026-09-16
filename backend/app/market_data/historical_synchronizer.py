from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.services.historical_data_service import HistoricalDataService
from app.services.mt5_bridge_service import MT5BridgeService
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


class HistoricalDataSynchronizer:
    """
    Background service responsible for keeping historical market data
    synchronized for the currently selected trading universe.

    The source of truth is:

        AccountSymbol.enabled == True

    Responsibilities:

    - Detect enabled trading symbols.
    - Synchronize historical candles for those symbols.
    - Re-check the trading universe periodically.
    - Stop synchronizing symbols once they are disabled.
    - Automatically resume synchronization when symbols are re-enabled.

    Historical candles are never deleted when a symbol is disabled.
    """

    def __init__(
        self,
        interval_seconds: int = 60,
        timeframe: str = "M15",
        count: int = 200,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.timeframe = timeframe
        self.count = count

        self._task: asyncio.Task | None = None
        self._running = False

        self._bridge_service = MT5BridgeService()

        self._historical_data_service = HistoricalDataService(
            session_factory=SessionLocal,
            bridge_service=self._bridge_service,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the historical-data synchronization loop.
        """

        if self._running:
            logger.warning("Historical data synchronizer is already running.")
            return

        self._running = True

        self._task = asyncio.create_task(
            self._run(),
            name="historical-data-synchronizer",
        )

        logger.info(
            "Historical data synchronizer started "
            "(interval=%ss, timeframe=%s, count=%s)",
            self.interval_seconds,
            self.timeframe,
            self.count,
        )

    async def stop(self) -> None:
        """
        Stop the historical-data synchronization loop cleanly.
        """

        if not self._running:
            return

        self._running = False

        if self._task is not None:
            self._task.cancel()

            try:
                await self._task

            except asyncio.CancelledError:
                pass

            finally:
                self._task = None

        logger.info("Historical data synchronizer stopped.")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """
        Main background synchronization loop.
        """

        while self._running:

            try:
                await self._synchronize()

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("Unexpected error in historical data synchronizer.")

            try:
                await asyncio.sleep(self.interval_seconds)

            except asyncio.CancelledError:
                raise

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------

    async def _synchronize(self) -> None:
        """
        Synchronize historical data for all currently enabled symbols.

        AccountSymbol.enabled is the authoritative trading-universe
        selection.
        """

        logger.debug("Starting historical-data synchronization.")

        # We need account IDs because the trading universe is
        # account-specific.
        account_ids = await self._get_account_ids()

        if not account_ids:
            logger.debug("No trading accounts found for historical synchronization.")
            return

        for account_id in account_ids:

            if not self._running:
                return

            try:
                result = await self._historical_data_service.sync_selected_symbols(
                    account_id=account_id,
                    timeframe=self.timeframe,
                    count=self.count,
                )

                logger.info(
                    "Historical synchronization completed "
                    "for account %s: selected=%s synchronized=%s failed=%s",
                    account_id,
                    result["symbols_selected"],
                    result["symbols_synchronized"],
                    result["symbols_failed"],
                )

            except Exception:
                logger.exception(
                    "Historical synchronization failed " "for account %s.",
                    account_id,
                )

    # ------------------------------------------------------------------
    # Account discovery
    # ------------------------------------------------------------------

    async def _get_account_ids(self) -> list:
        """
        Retrieve trading-account IDs that should be considered for
        historical synchronization.
        """

        from sqlalchemy import select

        from app.database.models.trading_account import TradingAccount

        async with SessionLocal() as session:

            result = await session.execute(select(TradingAccount.id))

            return list(result.scalars().all())


# Singleton used by the FastAPI application lifecycle.
historical_data_synchronizer = HistoricalDataSynchronizer()
