from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.trade import Trade


class AnalyticsRepository:
    """
    Read-only repository for analytics queries.

    Analytics are derived from immutable Trade records.
    No analytics records are written by this repository.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    # ==========================================================
    # ACCOUNT TRADES
    # ==========================================================

    async def get_account_trades(
        self,
        account_id: UUID,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .options(
                selectinload(
                    Trade.symbol
                )
            )
            .where(
                Trade.account_id == account_id
            )
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # ACCOUNT TRADES BY PERIOD
    # ==========================================================

    async def get_account_trades_by_period(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .options(
                selectinload(
                    Trade.symbol
                )
            )
            .where(
                Trade.account_id == account_id,
                Trade.closed_at >= start,
                Trade.closed_at < end,
            )
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )