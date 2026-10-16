from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models.symbol import Symbol
from app.database.session import SessionLocal
from app.events import EventBus, event_bus
from app.events.market import MarketTickEvent
from app.market_data.models import MarketCandle, MarketTick
from app.repositories.historical_candle_repository import (
    HistoricalCandleRepository,
)

logger = logging.getLogger(__name__)


class StrategyMarketDataView:
    """
    Read-only market-data adapter supplied to StrategyContext.

    Responsibilities:

        - cache the latest normalized live tick for each canonical symbol;
        - retrieve persisted historical candles by canonical symbol;
        - convert database candles into AQE-native MarketCandle objects;
        - keep strategies independent of SQLAlchemy and broker APIs.

    This component does not:

        - subscribe broker symbols;
        - consume Redis directly;
        - generate live candles;
        - evaluate strategies;
        - execute orders.

    Lifecycle is explicit. Call start() before enabling market-data
    consumption and stop() during runtime shutdown.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
        bus: EventBus | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._event_bus = bus if bus is not None else event_bus

        self._latest_ticks: dict[str, MarketTick] = {}
        self._started = False

    @property
    def started(self) -> bool:
        """Return whether the latest-tick cache is subscribed to EventBus."""
        return self._started

    async def start(self) -> None:
        """Subscribe to normalized market ticks."""
        if self._started:
            return

        await self._event_bus.subscribe(
            MarketTickEvent,
            self._on_tick,
        )

        self._started = True

        logger.info("Strategy market-data view started.")

    async def stop(self) -> None:
        """Unsubscribe and clear cached ticks."""
        if not self._started:
            return

        await self._event_bus.unsubscribe(
            MarketTickEvent,
            self._on_tick,
        )

        self._latest_ticks.clear()
        self._started = False

        logger.info("Strategy market-data view stopped.")

    async def _on_tick(self, event: MarketTickEvent) -> None:
        """Cache the latest tick for its canonical symbol."""
        tick = event.tick

        if not isinstance(tick, MarketTick):
            return

        if tick.validation_errors():
            logger.warning(
                "Ignoring invalid tick in strategy market-data view. " "symbol=%s",
                getattr(tick, "symbol", None),
            )
            return

        symbol_key = self._normalize_symbol(tick.symbol)

        existing = self._latest_ticks.get(symbol_key)

        # Duplicate or out-of-order ticks must not replace newer data.
        if existing is not None and tick.timestamp <= existing.timestamp:
            return

        self._latest_ticks[symbol_key] = tick

    async def get_latest_tick(self, symbol: str) -> MarketTick | None:
        """
        Return the latest cached tick for a canonical symbol.

        Returns None when no tick has been observed yet.
        """
        return self._latest_ticks.get(self._normalize_symbol(symbol))

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list[MarketCandle]:
        """
        Retrieve recent persisted candles in chronological order.

        This method is used by strategies during indicator warm-up.
        Database access occurs only when requested, not for every tick.
        """
        if count <= 0:
            raise ValueError("Candle count must be greater than zero.")

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_timeframe = self._normalize_timeframe(timeframe)

        async with self.session_factory() as session:
            symbol_id = await self._resolve_symbol_id(
                session=session,
                symbol=normalized_symbol,
            )

            if symbol_id is None:
                logger.warning(
                    "No active canonical symbol found for strategy "
                    "market-data request. symbol=%s",
                    normalized_symbol,
                )
                return []

            repository = HistoricalCandleRepository(session)

            records = await repository.latest(
                symbol_id=symbol_id,
                timeframe=normalized_timeframe,
                limit=count,
            )

            return [
                self._to_market_candle(
                    record,
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                )
                for record in records
            ]

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketCandle]:
        """Retrieve persisted candles in the requested UTC time range."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_timeframe = self._normalize_timeframe(timeframe)

        start_utc = self._normalize_datetime(start)
        end_utc = self._normalize_datetime(end)

        if start_utc >= end_utc:
            raise ValueError("Historical start must be earlier than end.")

        async with self.session_factory() as session:
            symbol_id = await self._resolve_symbol_id(
                session=session,
                symbol=normalized_symbol,
            )

            if symbol_id is None:
                logger.warning(
                    "No active canonical symbol found for historical "
                    "strategy data. symbol=%s",
                    normalized_symbol,
                )
                return []

            repository = HistoricalCandleRepository(session)

            records = await repository.list_range(
                symbol_id=symbol_id,
                timeframe=normalized_timeframe,
                start=start_utc,
                end=end_utc,
            )

            return [
                self._to_market_candle(
                    record,
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                )
                for record in records
            ]

    @staticmethod
    async def _resolve_symbol_id(
        *,
        session: AsyncSession,
        symbol: str,
    ):
        """Resolve the canonical AQE symbol name to its database ID."""
        result = await session.execute(
            select(Symbol.id).where(
                Symbol.name == symbol,
                Symbol.active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    def _to_market_candle(
        record: Any,
        *,
        symbol: str,
        timeframe: str,
    ) -> MarketCandle:
        """Convert a persisted HistoricalCandle into the strategy model."""
        timestamp = record.timestamp

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        return MarketCandle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=int(timestamp.timestamp()),
            open=float(record.open),
            high=float(record.high),
            low=float(record.low),
            close=float(record.close),
            volume=int(record.volume or 0),
            spread=int(record.spread or 0),
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("A non-empty canonical symbol is required.")

        return symbol.strip().upper()

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("A non-empty timeframe is required.")

        return timeframe.strip().upper()

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError("Historical range values must be datetimes.")

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


__all__ = ["StrategyMarketDataView"]
