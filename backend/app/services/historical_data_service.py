from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models.account_symbol import AccountSymbol
from app.database.models.historical_candle import HistoricalCandle
from app.database.models.symbol import Symbol
from app.repositories.historical_candle_repository import (
    HistoricalCandleRepository,
)
from app.services.mt5_bridge_service import MT5BridgeService

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """
    Service responsible for synchronizing and retrieving historical
    market data for an account's selected trading universe.

    AccountSymbol.enabled is the source of truth for which symbols
    should receive historical data.

    Historical candles are stored canonically against Symbol rather
    than AccountSymbol.

    There are two distinct synchronization modes:

    1. Incremental synchronization
       --------------------------
       Used by the normal background historical synchronizer.

    2. Historical backfill
       --------------------
       Used when a consumer such as the backtesting engine requires
       a specific historical range.

    Historical backfill is intentionally strict:

        - a selected symbol must return historical candles;
        - an empty MT5 response is treated as a failure;
        - malformed candle data is treated as a failure;
        - failures are surfaced to the caller;
        - successful symbols are committed independently.

    The backfill implementation uses an independent database session
    for each AccountSymbol. This is deliberate:

        - a failed symbol can safely rollback without expiring ORM
          objects needed by subsequent symbols;
        - AccountSymbol.symbol is never implicitly lazy-loaded;
        - the canonical Symbol is explicitly loaded with await;
        - each successful symbol gets its own transaction.

    This prevents the backtest loader from being the first component
    to discover that historical preparation silently failed.
    """

    # ==================================================================
    # TIMEFRAME DEFINITIONS
    # ==================================================================

    TIMEFRAME_DELTAS: dict[str, timedelta] = {
        "M1": timedelta(minutes=1),
        "M5": timedelta(minutes=5),
        "M15": timedelta(minutes=15),
        "M30": timedelta(minutes=30),
        "H1": timedelta(hours=1),
        "H4": timedelta(hours=4),
        "D1": timedelta(days=1),
    }

    DEFAULT_BACKFILL_CHUNK_DAYS = 7

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bridge_service: MT5BridgeService,
    ):
        self.session_factory = session_factory
        self.bridge_service = bridge_service

    # ==================================================================
    # PUBLIC SYNCHRONIZATION API
    # ==================================================================

    async def sync_selected_symbols(
        self,
        account_id: UUID,
        timeframe: str = "M15",
        count: int = 200,
    ) -> dict:
        """
        Synchronize historical candles for every enabled symbol.

        Initial synchronization retrieves the latest `count` candles.

        Incremental synchronization starts immediately after the latest
        persisted candle and continues through the current UTC time.
        """

        timeframe = self._normalize_timeframe(timeframe)

        if count <= 0:
            raise ValueError("count must be greater than zero.")

        async with self.session_factory() as session:
            account_symbols = await self._get_selected_symbols(
                session=session,
                account_id=account_id,
            )

            results: list[dict] = []

            for account_symbol in account_symbols:
                result = await self._sync_account_symbol(
                    session=session,
                    account_symbol=account_symbol,
                    timeframe=timeframe,
                    count=count,
                )

                results.append(result)

            await session.commit()

            successful = [result for result in results if result["status"] == "success"]

            failed = [result for result in results if result["status"] == "failed"]

            return {
                "account_id": account_id,
                "timeframe": timeframe,
                "requested_count": count,
                "symbols_selected": len(account_symbols),
                "symbols_synchronized": len(successful),
                "symbols_failed": len(failed),
                "results": results,
            }

    # ==================================================================
    # PUBLIC HISTORICAL BACKFILL API
    # ==================================================================

    async def backfill_selected_symbols(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
        timeframe: str = "M15",
        chunk_days: int = DEFAULT_BACKFILL_CHUNK_DAYS,
    ) -> dict:
        """
        Backfill historical candles for every enabled account symbol.

        Every selected symbol must successfully return historical data.

        A symbol returning zero candles is considered a failed backfill.

        Each AccountSymbol is processed using an independent database
        session and transaction.

        Successful symbols are committed independently so a later symbol
        failure does not discard already completed historical work.

        The returned result contains detailed per-symbol diagnostics.
        """

        timeframe = self._normalize_timeframe(timeframe)

        start = self._normalize_datetime(
            start,
            field_name="start",
        )

        end = self._normalize_datetime(
            end,
            field_name="end",
        )

        if start is None or end is None:
            raise ValueError(
                "Backfill start and end are required.",
            )

        if start >= end:
            raise ValueError(
                "Backfill start must be earlier than end.",
            )

        if chunk_days <= 0:
            raise ValueError(
                "chunk_days must be greater than zero.",
            )

        chunk_delta = timedelta(days=chunk_days)

        # --------------------------------------------------------------
        # First session is used ONLY to discover the selected universe.
        #
        # We immediately convert the ORM result into immutable scalar
        # identifiers before processing any symbols. The ORM objects are
        # never carried across transaction boundaries.
        # --------------------------------------------------------------

        async with self.session_factory() as session:
            account_symbols = await self._get_selected_symbols(
                session=session,
                account_id=account_id,
            )

            if not account_symbols:
                raise ValueError(
                    f"No enabled trading symbols are configured for "
                    f"account '{account_id}'.",
                )

            selected_symbol_ids = [
                account_symbol.id for account_symbol in account_symbols
            ]

        results: list[dict] = []

        # --------------------------------------------------------------
        # IMPORTANT:
        #
        # Every symbol gets its own AsyncSession.
        #
        # This prevents rollback() for one symbol from expiring ORM
        # objects belonging to another symbol.
        # --------------------------------------------------------------

        for account_symbol_id in selected_symbol_ids:
            async with self.session_factory() as session:
                try:
                    account_symbol = await self._get_selected_symbol_by_id(
                        session=session,
                        account_symbol_id=account_symbol_id,
                        account_id=account_id,
                    )

                    result = await self._backfill_account_symbol(
                        session=session,
                        account_symbol=account_symbol,
                        timeframe=timeframe,
                        start=start,
                        end=end,
                        chunk_delta=chunk_delta,
                    )

                    results.append(result)

                    if result["status"] == "success":
                        await session.commit()
                    else:
                        await session.rollback()

                except Exception as exc:
                    await session.rollback()

                    logger.exception(
                        "Unexpected historical backfill failure | "
                        "account_id=%s | account_symbol_id=%s",
                        account_id,
                        account_symbol_id,
                    )

                    results.append(
                        {
                            "status": "failed",
                            "account_symbol_id": account_symbol_id,
                            "symbol_id": None,
                            "symbol": None,
                            "broker_symbol": None,
                            "timeframe": timeframe,
                            "mode": "backfill",
                            "start": start,
                            "end": end,
                            "chunks_requested": 0,
                            "chunks_with_data": 0,
                            "chunks_without_data": 0,
                            "received": 0,
                            "new_candidates": 0,
                            "inserted": 0,
                            "earliest_timestamp": None,
                            "latest_timestamp": None,
                            "error": str(exc),
                        }
                    )

        successful = [result for result in results if result["status"] == "success"]

        failed = [result for result in results if result["status"] == "failed"]

        summary = {
            "account_id": account_id,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "chunk_days": chunk_days,
            "symbols_selected": len(selected_symbol_ids),
            "symbols_synchronized": len(successful),
            "symbols_failed": len(failed),
            "results": results,
        }

        logger.info(
            "Historical backfill completed | "
            "account_id=%s | timeframe=%s | "
            "selected=%s | successful=%s | failed=%s",
            account_id,
            timeframe,
            len(selected_symbol_ids),
            len(successful),
            len(failed),
        )

        # --------------------------------------------------------------
        # Do not allow BacktestComposition to continue when any selected
        # symbol could not be backfilled.
        # --------------------------------------------------------------

        if failed:
            failed_symbols = ", ".join(
                f"{result.get('broker_symbol') or result.get('symbol_id')}/"
                f"{result['timeframe']}"
                for result in failed
            )

            raise HistoricalBackfillError(
                "Historical backfill failed for "
                f"{len(failed)} symbol(s): {failed_symbols}. "
                f"account_id={account_id}.",
                results=results,
            )

        return summary

    async def backfill_symbol(
        self,
        account_id: UUID,
        symbol_id: UUID,
        start: datetime,
        end: datetime,
        timeframe: str = "M15",
        chunk_days: int = DEFAULT_BACKFILL_CHUNK_DAYS,
    ) -> dict:
        """
        Backfill one selected AccountSymbol over an explicit range.
        """

        timeframe = self._normalize_timeframe(timeframe)

        start = self._normalize_datetime(
            start,
            field_name="start",
        )

        end = self._normalize_datetime(
            end,
            field_name="end",
        )

        if start is None or end is None:
            raise ValueError(
                "Backfill start and end are required.",
            )

        if start >= end:
            raise ValueError(
                "Backfill start must be earlier than end.",
            )

        if chunk_days <= 0:
            raise ValueError(
                "chunk_days must be greater than zero.",
            )

        async with self.session_factory() as session:
            account_symbol = await self._get_selected_symbol_from_session(
                session=session,
                account_id=account_id,
                symbol_id=symbol_id,
            )

            result = await self._backfill_account_symbol(
                session=session,
                account_symbol=account_symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                chunk_delta=timedelta(days=chunk_days),
            )

            if result["status"] == "success":
                await session.commit()
            else:
                await session.rollback()

            return result

    # ==================================================================
    # RANGE BACKFILL IMPLEMENTATION
    # ==================================================================

    async def _backfill_account_symbol(
        self,
        session: AsyncSession,
        account_symbol: AccountSymbol,
        timeframe: str,
        start: datetime,
        end: datetime,
        chunk_delta: timedelta,
    ) -> dict:
        """
        Backfill one enabled AccountSymbol.

        The canonical Symbol is explicitly loaded using an awaited
        database operation. The method never accesses
        account_symbol.symbol, which would permit implicit lazy loading.

        Empty bridge responses are treated as failures.

        The method does not silently convert broker failures into
        successful backfills.
        """

        # --------------------------------------------------------------
        # Explicitly load the canonical Symbol.
        #
        # DO NOT use:
        #
        #     account_symbol.symbol
        #
        # because that is a lazy relationship and can trigger implicit
        # async database I/O from normal attribute access.
        # --------------------------------------------------------------

        symbol = await session.get(
            Symbol,
            account_symbol.symbol_id,
        )

        if symbol is None:
            raise HistoricalBackfillError(
                "Canonical symbol not found for AccountSymbol: "
                f"account_symbol_id={account_symbol.id}, "
                f"symbol_id={account_symbol.symbol_id}, "
                f"broker_symbol={account_symbol.broker_symbol}.",
            )

        repository = HistoricalCandleRepository(session)

        current_start = start

        total_received = 0
        total_candidates = 0
        total_inserted = 0
        chunks_requested = 0
        chunks_with_data = 0
        chunks_without_data = 0

        earliest_timestamp: datetime | None = None
        latest_timestamp: datetime | None = None

        broker_symbol = (
            account_symbol.broker_symbol.strip() if account_symbol.broker_symbol else ""
        )

        try:
            if not broker_symbol:
                raise ValueError(
                    f"AccountSymbol '{account_symbol.id}' has no " "broker symbol.",
                )

            logger.info(
                "Starting historical backfill | "
                "symbol=%s | broker_symbol=%s | timeframe=%s | "
                "start=%s | end=%s",
                symbol.name,
                broker_symbol,
                timeframe,
                start.isoformat(),
                end.isoformat(),
            )

            while current_start <= end:
                chunk_end = min(
                    current_start + chunk_delta,
                    end,
                )

                chunks_requested += 1

                logger.debug(
                    "Requesting historical candles | "
                    "symbol=%s | timeframe=%s | start=%s | end=%s",
                    broker_symbol,
                    timeframe,
                    current_start.isoformat(),
                    chunk_end.isoformat(),
                )

                candles = await self.bridge_service.get_candles(
                    symbol=broker_symbol,
                    timeframe=timeframe,
                    start=current_start,
                    end=chunk_end,
                )

                received = len(candles)

                total_received += received

                logger.info(
                    "Historical bridge response | "
                    "symbol=%s | timeframe=%s | "
                    "start=%s | end=%s | candles=%s",
                    broker_symbol,
                    timeframe,
                    current_start.isoformat(),
                    chunk_end.isoformat(),
                    received,
                )

                # ------------------------------------------------------
                # Empty response is NOT success.
                # ------------------------------------------------------

                if not candles:
                    chunks_without_data += 1

                    raise HistoricalBackfillError(
                        "MT5 returned no historical candles for "
                        f"symbol={broker_symbol}, "
                        f"timeframe={timeframe}, "
                        f"range={current_start.isoformat()}.."
                        f"{chunk_end.isoformat()}.",
                    )

                chunks_with_data += 1

                normalized = self._normalize_candles(
                    candles=candles,
                    symbol_id=symbol.id,
                    timeframe=timeframe,
                )

                chunk_candidates = [
                    candle
                    for candle in normalized
                    if (
                        candle["timestamp"] >= current_start
                        and candle["timestamp"] <= chunk_end
                    )
                ]

                chunk_candidates.sort(
                    key=lambda candle: candle["timestamp"],
                )

                if not chunk_candidates:
                    raise HistoricalBackfillError(
                        "MT5 returned candles for "
                        f"{broker_symbol}, but none were usable "
                        "inside requested range "
                        f"{current_start.isoformat()}.."
                        f"{chunk_end.isoformat()}.",
                    )

                total_candidates += len(chunk_candidates)

                inserted = await repository.upsert_many(
                    chunk_candidates,
                )

                total_inserted += inserted

                first_timestamp = chunk_candidates[0]["timestamp"]
                last_timestamp = chunk_candidates[-1]["timestamp"]

                if earliest_timestamp is None or first_timestamp < earliest_timestamp:
                    earliest_timestamp = first_timestamp

                if latest_timestamp is None or last_timestamp > latest_timestamp:
                    latest_timestamp = last_timestamp

                logger.info(
                    "Historical chunk persisted | "
                    "symbol=%s | timeframe=%s | "
                    "candidates=%s | inserted=%s | "
                    "first=%s | last=%s",
                    broker_symbol,
                    timeframe,
                    len(chunk_candidates),
                    inserted,
                    first_timestamp.isoformat(),
                    last_timestamp.isoformat(),
                )

                if chunk_end >= end:
                    break

                next_start = chunk_end

                if next_start <= current_start:
                    raise RuntimeError(
                        "Historical backfill failed to advance its "
                        f"range cursor for {broker_symbol}.",
                    )

                current_start = next_start

            if total_candidates == 0:
                raise HistoricalBackfillError(
                    "Historical backfill produced zero usable candles "
                    f"for {broker_symbol}/{timeframe}.",
                )

            logger.info(
                "Historical backfill succeeded | "
                "symbol=%s | timeframe=%s | "
                "chunks=%s | received=%s | "
                "candidates=%s | inserted=%s | "
                "first=%s | last=%s",
                broker_symbol,
                timeframe,
                chunks_requested,
                total_received,
                total_candidates,
                total_inserted,
                (earliest_timestamp.isoformat() if earliest_timestamp else None),
                (latest_timestamp.isoformat() if latest_timestamp else None),
            )

            return {
                "status": "success",
                "account_symbol_id": account_symbol.id,
                "symbol_id": symbol.id,
                "symbol": symbol.name,
                "broker_symbol": broker_symbol,
                "timeframe": timeframe,
                "mode": "backfill",
                "start": start,
                "end": end,
                "chunks_requested": chunks_requested,
                "chunks_with_data": chunks_with_data,
                "chunks_without_data": chunks_without_data,
                "received": total_received,
                "new_candidates": total_candidates,
                "inserted": total_inserted,
                "earliest_timestamp": earliest_timestamp,
                "latest_timestamp": latest_timestamp,
                "message": "Historical data backfill completed.",
            }

        except Exception as exc:
            logger.exception(
                "Historical backfill failed | "
                "symbol=%s | broker_symbol=%s | timeframe=%s | "
                "start=%s | end=%s",
                symbol.name,
                broker_symbol,
                timeframe,
                start.isoformat(),
                end.isoformat(),
            )

            return {
                "status": "failed",
                "account_symbol_id": account_symbol.id,
                "symbol_id": symbol.id,
                "symbol": symbol.name,
                "broker_symbol": broker_symbol,
                "timeframe": timeframe,
                "mode": "backfill",
                "start": start,
                "end": end,
                "chunks_requested": chunks_requested,
                "chunks_with_data": chunks_with_data,
                "chunks_without_data": chunks_without_data,
                "received": total_received,
                "new_candidates": total_candidates,
                "inserted": total_inserted,
                "earliest_timestamp": earliest_timestamp,
                "latest_timestamp": latest_timestamp,
                "error": str(exc),
            }

    # ==================================================================
    # SYMBOL SYNCHRONIZATION
    # ==================================================================

    async def _sync_account_symbol(
        self,
        session: AsyncSession,
        account_symbol: AccountSymbol,
        timeframe: str,
        count: int,
    ) -> dict:
        """
        Synchronize historical data for one enabled AccountSymbol.

        The canonical Symbol is explicitly loaded rather than accessed
        through a lazy relationship.
        """

        symbol = await session.get(
            Symbol,
            account_symbol.symbol_id,
        )

        if symbol is None:
            raise ValueError(
                "Canonical symbol not found for AccountSymbol: "
                f"account_symbol_id={account_symbol.id}, "
                f"symbol_id={account_symbol.symbol_id}.",
            )

        repository = HistoricalCandleRepository(session)

        latest_candle: HistoricalCandle | None = None

        try:
            latest_candle = await self._get_latest_persisted_candle(
                repository=repository,
                symbol_id=symbol.id,
                timeframe=timeframe,
            )

            # ----------------------------------------------------------
            # INITIAL
            # ----------------------------------------------------------

            if latest_candle is None:
                candles = await self.bridge_service.get_candles(
                    symbol=account_symbol.broker_symbol,
                    timeframe=timeframe,
                    count=count,
                )

                if not candles:
                    raise ValueError(
                        "MT5 returned no historical candles for "
                        f"{account_symbol.broker_symbol}/{timeframe}.",
                    )

                normalized = self._normalize_candles(
                    candles=candles,
                    symbol_id=symbol.id,
                    timeframe=timeframe,
                )

                normalized.sort(
                    key=lambda candle: candle["timestamp"],
                )

                inserted = await repository.upsert_many(
                    normalized,
                )

                latest_timestamp = normalized[-1]["timestamp"] if normalized else None

                return {
                    "status": "success",
                    "symbol_id": symbol.id,
                    "symbol": symbol.name,
                    "broker_symbol": account_symbol.broker_symbol,
                    "timeframe": timeframe,
                    "mode": "initial",
                    "requested": count,
                    "received": len(candles),
                    "new_candidates": len(normalized),
                    "inserted": inserted,
                    "existing_latest": None,
                    "latest_timestamp": latest_timestamp,
                    "start": None,
                    "end": None,
                    "message": "Historical data initialized.",
                }

            # ----------------------------------------------------------
            # INCREMENTAL
            # ----------------------------------------------------------

            next_timestamp = self._next_candle_timestamp(
                latest_timestamp=latest_candle.timestamp,
                timeframe=timeframe,
            )

            now = datetime.now(timezone.utc)

            if next_timestamp > now:
                return {
                    "status": "success",
                    "symbol_id": symbol.id,
                    "symbol": symbol.name,
                    "broker_symbol": account_symbol.broker_symbol,
                    "timeframe": timeframe,
                    "mode": "incremental",
                    "requested": 0,
                    "received": 0,
                    "new_candidates": 0,
                    "inserted": 0,
                    "existing_latest": latest_candle.timestamp,
                    "latest_timestamp": latest_candle.timestamp,
                    "start": next_timestamp,
                    "end": now,
                    "message": "Historical data is already up to date.",
                }

            candles = await self.bridge_service.get_candles(
                symbol=account_symbol.broker_symbol,
                timeframe=timeframe,
                start=next_timestamp,
                end=now,
            )

            if not candles:
                return {
                    "status": "success",
                    "symbol_id": symbol.id,
                    "symbol": symbol.name,
                    "broker_symbol": account_symbol.broker_symbol,
                    "timeframe": timeframe,
                    "mode": "incremental",
                    "requested": 0,
                    "received": 0,
                    "new_candidates": 0,
                    "inserted": 0,
                    "existing_latest": latest_candle.timestamp,
                    "latest_timestamp": latest_candle.timestamp,
                    "start": next_timestamp,
                    "end": now,
                    "message": "No new historical candles returned.",
                }

            normalized = self._normalize_candles(
                candles=candles,
                symbol_id=symbol.id,
                timeframe=timeframe,
            )

            normalized.sort(
                key=lambda candle: candle["timestamp"],
            )

            new_candidates = [
                candle
                for candle in normalized
                if (
                    candle["timestamp"] >= next_timestamp and candle["timestamp"] <= now
                )
            ]

            inserted = await repository.upsert_many(
                new_candidates,
            )

            latest_timestamp = (
                new_candidates[-1]["timestamp"]
                if new_candidates
                else latest_candle.timestamp
            )

            return {
                "status": "success",
                "symbol_id": symbol.id,
                "symbol": symbol.name,
                "broker_symbol": account_symbol.broker_symbol,
                "timeframe": timeframe,
                "mode": "incremental",
                "requested": len(new_candidates),
                "received": len(candles),
                "new_candidates": len(new_candidates),
                "inserted": inserted,
                "existing_latest": latest_candle.timestamp,
                "latest_timestamp": latest_timestamp,
                "start": next_timestamp,
                "end": now,
                "message": "Historical data synchronized incrementally.",
            }

        except Exception as exc:
            logger.exception(
                "Historical synchronization failed | "
                "symbol=%s | broker_symbol=%s | timeframe=%s",
                symbol.name,
                account_symbol.broker_symbol,
                timeframe,
            )

            return {
                "status": "failed",
                "symbol_id": symbol.id,
                "symbol": symbol.name,
                "broker_symbol": account_symbol.broker_symbol,
                "timeframe": timeframe,
                "mode": ("initial" if latest_candle is None else "incremental"),
                "requested": count,
                "received": 0,
                "new_candidates": 0,
                "inserted": 0,
                "existing_latest": (
                    latest_candle.timestamp if latest_candle is not None else None
                ),
                "latest_timestamp": None,
                "start": None,
                "end": None,
                "error": str(exc),
            }

    # ==================================================================
    # LATEST PERSISTED CANDLE
    # ==================================================================

    async def _get_latest_persisted_candle(
        self,
        repository: HistoricalCandleRepository,
        symbol_id: UUID,
        timeframe: str,
    ) -> HistoricalCandle | None:
        """
        Retrieve the newest persisted candle.
        """

        candles = await repository.latest(
            symbol_id=symbol_id,
            timeframe=timeframe,
            limit=1,
        )

        if not candles:
            return None

        return candles[-1]

    # ==================================================================
    # NEXT CANDLE
    # ==================================================================

    @classmethod
    def _next_candle_timestamp(
        cls,
        latest_timestamp: datetime,
        timeframe: str,
    ) -> datetime:
        """
        Calculate the timestamp immediately following the latest
        persisted candle.
        """

        timeframe = cls._normalize_timeframe(timeframe)

        delta = cls.TIMEFRAME_DELTAS.get(timeframe)

        if delta is None:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}",
            )

        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.replace(
                tzinfo=timezone.utc,
            )
        else:
            latest_timestamp = latest_timestamp.astimezone(
                timezone.utc,
            )

        return latest_timestamp + delta

    # ==================================================================
    # TRADING UNIVERSE
    # ==================================================================

    async def _get_selected_symbols(
        self,
        session: AsyncSession,
        account_id: UUID,
    ) -> list[AccountSymbol]:
        """
        Return only enabled symbols for the account.

        No relationship loading is requested here. The service uses
        symbol_id and broker_symbol explicitly and loads Symbol with
        an awaited query when required.
        """

        result = await session.execute(
            select(AccountSymbol)
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.enabled.is_(True),
            )
            .order_by(
                AccountSymbol.broker_symbol.asc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def _get_selected_symbol_by_id(
        self,
        session: AsyncSession,
        account_symbol_id: UUID,
        account_id: UUID,
    ) -> AccountSymbol:
        """
        Retrieve one enabled AccountSymbol by its primary key.

        The query intentionally does not use a lazy relationship.
        """

        result = await session.execute(
            select(AccountSymbol).where(
                AccountSymbol.id == account_symbol_id,
                AccountSymbol.account_id == account_id,
                AccountSymbol.enabled.is_(True),
            )
        )

        account_symbol = result.scalar_one_or_none()

        if account_symbol is None:
            raise ValueError(
                "Selected trading symbol no longer exists or is disabled: "
                f"account_id={account_id}, "
                f"account_symbol_id={account_symbol_id}",
            )

        return account_symbol

    async def _get_selected_symbol_from_session(
        self,
        session: AsyncSession,
        account_id: UUID,
        symbol_id: UUID,
    ) -> AccountSymbol:
        """
        Retrieve one enabled AccountSymbol.
        """

        result = await session.execute(
            select(AccountSymbol).where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.symbol_id == symbol_id,
                AccountSymbol.enabled.is_(True),
            )
        )

        account_symbol = result.scalar_one_or_none()

        if account_symbol is None:
            raise ValueError(
                "Selected trading symbol not found for account: "
                f"account_id={account_id}, "
                f"symbol_id={symbol_id}",
            )

        return account_symbol

    async def get_selected_symbol(
        self,
        account_id: UUID,
        symbol_id: UUID,
    ) -> AccountSymbol:
        """
        Return one enabled account symbol.
        """

        async with self.session_factory() as session:
            return await self._get_selected_symbol_from_session(
                session=session,
                account_id=account_id,
                symbol_id=symbol_id,
            )

    # ==================================================================
    # HISTORICAL DATA READ API
    # ==================================================================

    async def get_candles(
        self,
        symbol_id: UUID,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[HistoricalCandle]:
        """
        Retrieve persisted historical candles.
        """

        timeframe = self._normalize_timeframe(
            timeframe,
        )

        async with self.session_factory() as session:
            repository = HistoricalCandleRepository(
                session,
            )

            return await repository.list_range(
                symbol_id=symbol_id,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )

    async def get_latest_candles(
        self,
        symbol_id: UUID,
        timeframe: str,
        limit: int = 200,
    ) -> list[HistoricalCandle]:
        """
        Retrieve the latest persisted historical candles.
        """

        timeframe = self._normalize_timeframe(
            timeframe,
        )

        async with self.session_factory() as session:
            repository = HistoricalCandleRepository(
                session,
            )

            return await repository.latest(
                symbol_id=symbol_id,
                timeframe=timeframe,
                limit=limit,
            )

    async def get_symbol(
        self,
        symbol_id: UUID,
    ) -> Symbol:
        """
        Retrieve an active canonical symbol.
        """

        async with self.session_factory() as session:
            result = await session.execute(
                select(Symbol).where(
                    Symbol.id == symbol_id,
                    Symbol.active.is_(True),
                )
            )

            symbol = result.scalar_one_or_none()

            if symbol is None:
                raise ValueError(
                    f"Active symbol not found: {symbol_id}",
                )

            return symbol

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_candles(
        candles: list[dict],
        symbol_id: UUID,
        timeframe: str,
    ) -> list[dict]:
        """
        Convert MT5 Bridge candle payloads into the canonical
        historical_candles representation.
        """

        normalized: list[dict] = []

        for candle in candles:
            if not isinstance(candle, dict):
                raise ValueError(
                    "Historical candle payload must be a dictionary.",
                )

            timestamp = candle.get("timestamp")

            if timestamp is None:
                timestamp = candle.get("time")

            if timestamp is None:
                raise ValueError(
                    "Historical candle is missing timestamp/time.",
                )

            timestamp = HistoricalDataService._normalize_timestamp(
                timestamp,
            )

            try:
                open_price = candle["open"]
                high_price = candle["high"]
                low_price = candle["low"]
                close_price = candle["close"]

            except KeyError as exc:
                raise ValueError(
                    "Historical candle is missing required field: " f"{exc}",
                ) from exc

            volume = candle.get("volume")

            if volume is None:
                volume = candle.get("tick_volume")

            if volume is None:
                volume = candle.get(
                    "real_volume",
                    0,
                )

            normalized.append(
                {
                    "symbol_id": symbol_id,
                    "timeframe": timeframe,
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "spread": candle.get("spread"),
                }
            )

        return normalized

    # ==================================================================
    # TIMEFRAME
    # ==================================================================

    @classmethod
    def _normalize_timeframe(
        cls,
        timeframe: str,
    ) -> str:
        """
        Normalize and validate timeframe.
        """

        if not isinstance(
            timeframe,
            str,
        ):
            raise ValueError(
                "Timeframe must be a string.",
            )

        normalized = timeframe.upper().strip()

        if normalized not in cls.TIMEFRAME_DELTAS:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}",
            )

        return normalized

    # ==================================================================
    # DATETIME
    # ==================================================================

    @staticmethod
    def _normalize_datetime(
        value: datetime | None,
        field_name: str,
    ) -> datetime | None:
        """
        Normalize a datetime to timezone-aware UTC.

        Naive datetimes are interpreted as UTC.
        """

        if value is None:
            return None

        if not isinstance(
            value,
            datetime,
        ):
            raise ValueError(
                f"{field_name} must be a datetime.",
            )

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @staticmethod
    def _normalize_timestamp(
        timestamp,
    ) -> datetime:
        """
        Normalize supported timestamp formats into UTC-aware
        datetimes.
        """

        if isinstance(
            timestamp,
            datetime,
        ):
            result = timestamp

        elif isinstance(
            timestamp,
            str,
        ):
            result = datetime.fromisoformat(
                timestamp.replace(
                    "Z",
                    "+00:00",
                )
            )

        elif isinstance(
            timestamp,
            (int, float),
        ):
            result = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        else:
            raise ValueError(
                "Unsupported historical candle timestamp type: "
                f"{type(timestamp).__name__}",
            )

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=timezone.utc,
            )
        else:
            result = result.astimezone(
                timezone.utc,
            )

        return result


# ======================================================================
# EXCEPTIONS
# ======================================================================


class HistoricalBackfillError(RuntimeError):
    """
    Raised when historical data preparation cannot satisfy a requested
    backfill.

    ``results`` contains per-symbol diagnostics when available.
    """

    def __init__(
        self,
        message: str,
        *,
        results: list[dict] | None = None,
    ):
        super().__init__(message)
        self.results = results or []
