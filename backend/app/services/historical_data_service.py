from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.database.models.account_symbol import AccountSymbol
from app.database.models.historical_candle import HistoricalCandle
from app.database.models.symbol import Symbol
from app.repositories.historical_candle_repository import (
    HistoricalCandleRepository,
)
from app.services.mt5_bridge_service import MT5BridgeService


class HistoricalDataService:
    """
    Service responsible for synchronizing and retrieving historical
    market data for an account's selected trading universe.

    AccountSymbol.enabled is the source of truth for which symbols
    should receive historical data.

    Historical candles are stored canonically against Symbol rather
    than AccountSymbol.

    Synchronization behavior:

    1. If no historical data exists:
       - request the latest `count` candles from the MT5 Bridge.

    2. If historical data already exists:
       - find the latest persisted candle.
       - calculate the next candle timestamp.
       - request only the range from that timestamp until now.

    3. Existing candles are never deleted by synchronization.

    4. Disabled AccountSymbols are never synchronized.
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
        Synchronize historical candles for every currently enabled
        symbol belonging to the specified trading account.

        Only:

            AccountSymbol.enabled == True

        symbols are synchronized.
        """

        timeframe = self._normalize_timeframe(timeframe)

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
        Synchronize historical candles for one enabled AccountSymbol.

        Initial synchronization:
            latest N candles.

        Incremental synchronization:
            latest persisted candle + timeframe
            through the current UTC time.
        """

        # `AccountSymbol.symbol` is eagerly loaded by
        # `_get_selected_symbols()`.
        symbol = account_symbol.symbol

        repository = HistoricalCandleRepository(session)

        latest_candle: HistoricalCandle | None = None

        try:
            # ----------------------------------------------------------
            # Find the latest persisted candle.
            # ----------------------------------------------------------

            latest_candle = await self._get_latest_persisted_candle(
                repository=repository,
                symbol_id=symbol.id,
                timeframe=timeframe,
            )

            # ----------------------------------------------------------
            # INITIAL SYNCHRONIZATION
            # ----------------------------------------------------------

            if latest_candle is None:

                candles = await self.bridge_service.get_candles(
                    symbol=account_symbol.broker_symbol,
                    timeframe=timeframe,
                    count=count,
                )

                normalized = self._normalize_candles(
                    candles=candles,
                    symbol_id=symbol.id,
                    timeframe=timeframe,
                )

                normalized.sort(key=lambda candle: candle["timestamp"])

                inserted = await repository.upsert_many(normalized)

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
            # INCREMENTAL SYNCHRONIZATION
            # ----------------------------------------------------------

            next_timestamp = self._next_candle_timestamp(
                latest_timestamp=latest_candle.timestamp,
                timeframe=timeframe,
            )

            now = datetime.now(timezone.utc)

            # ----------------------------------------------------------
            # Nothing to synchronize yet.
            # ----------------------------------------------------------

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

            # ----------------------------------------------------------
            # Request only the missing range.
            # ----------------------------------------------------------

            candles = await self.bridge_service.get_candles(
                symbol=account_symbol.broker_symbol,
                timeframe=timeframe,
                start=next_timestamp,
                end=now,
            )

            normalized = self._normalize_candles(
                candles=candles,
                symbol_id=symbol.id,
                timeframe=timeframe,
            )

            normalized.sort(key=lambda candle: candle["timestamp"])

            # ----------------------------------------------------------
            # Safety filter.
            # ----------------------------------------------------------

            new_candidates = [
                candle
                for candle in normalized
                if (
                    candle["timestamp"] >= next_timestamp and candle["timestamp"] <= now
                )
            ]

            inserted = await repository.upsert_many(new_candidates)

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
        Retrieve the newest persisted candle for a
        symbol/timeframe.
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
    # NEXT CANDLE CALCULATION
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
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if latest_timestamp.tzinfo is None:

            latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)

        else:

            latest_timestamp = latest_timestamp.astimezone(timezone.utc)

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
        Return only symbols currently enabled for trading.

        AccountSymbol.enabled is the authoritative trading-universe
        selection.

        The Symbol relationship is eagerly loaded because this service
        uses AsyncSession and must not trigger implicit lazy-loading.
        """

        result = await session.execute(
            select(AccountSymbol)
            .options(selectinload(AccountSymbol.symbol))
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.enabled.is_(True),
            )
            .order_by(AccountSymbol.broker_symbol.asc())
        )

        return list(result.scalars().all())

    async def get_selected_symbol(
        self,
        account_id: UUID,
        symbol_id: UUID,
    ) -> AccountSymbol:
        """
        Return a symbol only if it is currently enabled for the
        specified trading account.

        The Symbol relationship is eagerly loaded to prevent
        MissingGreenlet errors when callers access `.symbol`.
        """

        async with self.session_factory() as session:

            result = await session.execute(
                select(AccountSymbol)
                .options(selectinload(AccountSymbol.symbol))
                .where(
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
                    f"symbol_id={symbol_id}"
                )

            return account_symbol

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
        Retrieve persisted historical candles for a symbol.
        """

        timeframe = self._normalize_timeframe(timeframe)

        async with self.session_factory() as session:

            repository = HistoricalCandleRepository(session)

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

        Results are returned chronologically.
        """

        timeframe = self._normalize_timeframe(timeframe)

        async with self.session_factory() as session:

            repository = HistoricalCandleRepository(session)

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
                raise ValueError(f"Active symbol not found: {symbol_id}")

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
        historical_candles database representation.
        """

        normalized: list[dict] = []

        for candle in candles:

            if not isinstance(candle, dict):
                raise ValueError("Historical candle payload must be a dictionary")

            timestamp = candle.get("timestamp")

            if timestamp is None:
                timestamp = candle.get("time")

            if timestamp is None:
                raise ValueError("Historical candle is missing timestamp/time")

            timestamp = HistoricalDataService._normalize_timestamp(timestamp)

            try:
                open_price = candle["open"]
                high_price = candle["high"]
                low_price = candle["low"]
                close_price = candle["close"]

            except KeyError as exc:

                raise ValueError(
                    "Historical candle is missing required " f"field: {exc}"
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
    # TIMEFRAME VALIDATION
    # ==================================================================

    @classmethod
    def _normalize_timeframe(
        cls,
        timeframe: str,
    ) -> str:
        """
        Normalize and validate a timeframe.
        """

        if not isinstance(
            timeframe,
            str,
        ):
            raise ValueError("Timeframe must be a string.")

        normalized = timeframe.upper().strip()

        if normalized not in cls.TIMEFRAME_DELTAS:
            raise ValueError("Unsupported timeframe: " f"{timeframe}")

        return normalized

    # ==================================================================
    # TIMESTAMP NORMALIZATION
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
                f"{type(timestamp).__name__}"
            )

        if result.tzinfo is None:

            result = result.replace(tzinfo=timezone.utc)

        else:

            result = result.astimezone(timezone.utc)

        return result
