from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.historical_candle import HistoricalCandle


class HistoricalCandleRepository:
    """
    Repository responsible for persistence and retrieval of historical
    market candles.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_many(
        self,
        candles: list[dict],
    ) -> int:
        """
        Insert historical candles while ignoring duplicates.

        A candle is uniquely identified by:

            symbol_id + timeframe + timestamp

        Returns the number of rows inserted.
        """

        if not candles:
            return 0

        statement = insert(HistoricalCandle).values(candles)

        statement = statement.on_conflict_do_nothing(
            constraint="uq_historical_candle_symbol_timeframe_timestamp",
        )

        result = await self.session.execute(statement)

        return result.rowcount or 0

    async def get_by_timestamp(
        self,
        symbol_id: UUID,
        timeframe: str,
        timestamp: datetime,
    ) -> HistoricalCandle | None:
        """
        Retrieve a single candle by its unique identity.
        """

        result = await self.session.execute(
            select(HistoricalCandle).where(
                HistoricalCandle.symbol_id == symbol_id,
                HistoricalCandle.timeframe == timeframe,
                HistoricalCandle.timestamp == timestamp,
            )
        )

        return result.scalar_one_or_none()

    async def list_range(
        self,
        symbol_id: UUID,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[HistoricalCandle]:
        """
        Retrieve historical candles ordered chronologically.
        """

        statement = (
            select(HistoricalCandle)
            .where(
                HistoricalCandle.symbol_id == symbol_id,
                HistoricalCandle.timeframe == timeframe,
            )
            .order_by(HistoricalCandle.timestamp.asc())
        )

        if start is not None:
            statement = statement.where(
                HistoricalCandle.timestamp >= start
            )

        if end is not None:
            statement = statement.where(
                HistoricalCandle.timestamp <= end
            )

        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def latest(
        self,
        symbol_id: UUID,
        timeframe: str,
        limit: int = 200,
    ) -> list[HistoricalCandle]:
        """
        Retrieve the most recent candles in chronological order.
        """

        statement = (
            select(HistoricalCandle)
            .where(
                HistoricalCandle.symbol_id == symbol_id,
                HistoricalCandle.timeframe == timeframe,
            )
            .order_by(HistoricalCandle.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(statement)

        candles = list(result.scalars().all())

        candles.reverse()

        return candles

    async def delete_range(
        self,
        symbol_id: UUID,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """
        Delete historical candles within an optional time range.
        """

        statement = delete(HistoricalCandle).where(
            HistoricalCandle.symbol_id == symbol_id,
            HistoricalCandle.timeframe == timeframe,
        )

        if start is not None:
            statement = statement.where(
                HistoricalCandle.timestamp >= start
            )

        if end is not None:
            statement = statement.where(
                HistoricalCandle.timestamp <= end
            )

        result = await self.session.execute(statement)

        return result.rowcount or 0