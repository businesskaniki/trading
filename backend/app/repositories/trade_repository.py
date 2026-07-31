from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TradeResult
from app.database.models.trade import Trade


class TradeRepository:
    """
    Repository responsible for Trade database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    async def create(self, **kwargs) -> Trade:
        trade = Trade(**kwargs)

        self.db.add(trade)

        await self.db.commit()
        await self.db.refresh(trade)

        return trade

    # ---------------------------------------------------------
    # Get
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        trade_id: UUID,
    ) -> Trade | None:

        result = await self.db.execute(
            select(Trade).where(
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
                Trade.closed_at.desc()
            )
        )

        return list(result.scalars().all())

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
                Trade.closed_at.desc()
            )
        )

        return list(result.scalars().all())

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
                Trade.closed_at.desc()
            )
        )

        return list(result.scalars().all())

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
                Trade.closed_at.desc()
            )
        )

        return list(result.scalars().all())

    async def get_latest(self) -> Trade | None:

        result = await self.db.execute(
            select(Trade)
            .order_by(
                Trade.closed_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_all(self) -> list[Trade]:

        result = await self.db.execute(
            select(Trade)
            .order_by(
                Trade.closed_at.desc()
            )
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    async def update(
        self,
        trade: Trade,
        **kwargs,
    ) -> Trade:

        for key, value in kwargs.items():
            setattr(trade, key, value)

        await self.db.commit()
        await self.db.refresh(trade)

        return trade

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    async def delete(
        self,
        trade: Trade,
    ) -> None:

        await self.db.delete(trade)
        await self.db.commit()

    # ---------------------------------------------------------
    # Utility
    # ---------------------------------------------------------

    async def exists(
        self,
        trade_id: UUID,
    ) -> bool:

        return (
            await self.get_by_id(trade_id)
        ) is not None