from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import TradeResult
from app.database.models.trade import Trade


class TradeRepository:
    """
    Repository responsible for Trade persistence and retrieval.

    Trades are immutable records.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create(
        self,
        commit: bool = True,
        **data,
    ) -> Trade:

        trade = Trade(**data)

        self.db.add(trade)

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(trade)

        return trade

    # ==========================================================
    # READ
    # ==========================================================

    async def get_by_id(
        self,
        trade_id: UUID,
    ) -> Trade | None:

        result = await self.db.execute(
            select(Trade)
            .options(
                selectinload(Trade.position),
                selectinload(Trade.account),
                selectinload(Trade.symbol),
            )
            .where(
                Trade.id == trade_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_ticket(
        self,
        ticket: int,
    ) -> Trade | None:

        result = await self.db.execute(
            select(Trade).where(
                Trade.ticket == ticket
            )
        )

        return result.scalar_one_or_none()

    async def get_by_position(
        self,
        position_id: UUID,
    ) -> Trade | None:

        result = await self.db.execute(
            select(Trade).where(
                Trade.position_id == position_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_account(
        self,
        account_id: UUID,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
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

    async def get_by_symbol(
        self,
        symbol_id: UUID,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .where(
                Trade.symbol_id == symbol_id
            )
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_by_strategy(
        self,
        strategy: str,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .where(
                Trade.strategy == strategy
            )
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_by_result(
        self,
        result_type: TradeResult,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .where(
                Trade.result == result_type
            )
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_latest(
        self,
    ) -> Trade | None:

        result = await self.db.execute(
            select(Trade)
            .order_by(
                Trade.closed_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .order_by(
                Trade.closed_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # PERFORMANCE / ANALYTICS QUERIES
    # ==========================================================

    async def get_by_account_and_period(
        self,
        account_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
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

    async def get_by_strategy_and_period(
        self,
        strategy: str,
        start: datetime,
        end: datetime,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .where(
                Trade.strategy == strategy,
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

    async def get_by_symbol_and_period(
        self,
        symbol_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .where(
                Trade.symbol_id == symbol_id,
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

    # ==========================================================
    # EXISTS
    # ==========================================================

    async def exists_by_ticket(
        self,
        ticket: int,
    ) -> bool:

        result = await self.db.execute(
            select(Trade.id)
            .where(
                Trade.ticket == ticket
            )
            .limit(1)
        )

        return (
            result.scalar_one_or_none()
            is not None
        )

    async def exists_by_position(
        self,
        position_id: UUID,
    ) -> bool:

        result = await self.db.execute(
            select(Trade.id)
            .where(
                Trade.position_id == position_id
            )
            .limit(1)
        )

        return (
            result.scalar_one_or_none()
            is not None
        )