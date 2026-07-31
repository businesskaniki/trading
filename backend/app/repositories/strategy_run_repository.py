from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.strategy_run import StrategyRun
from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType


class StrategyRunRepository:
    """
    Repository responsible for StrategyRun database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    async def create(self, **kwargs) -> StrategyRun:
        strategy_run = StrategyRun(**kwargs)

        self.db.add(strategy_run)

        await self.db.commit()
        await self.db.refresh(strategy_run)

        return strategy_run

    # ---------------------------------------------------------
    # Get
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        strategy_run_id: UUID,
    ) -> StrategyRun | None:

        result = await self.db.execute(
            select(StrategyRun).where(
                StrategyRun.id == strategy_run_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        strategy_name: str,
    ) -> list[StrategyRun]:

        result = await self.db.execute(
            select(StrategyRun)
            .where(
                StrategyRun.strategy_name == strategy_name
            )
            .order_by(
                StrategyRun.started_at.desc()
            )
        )

        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: StrategyRunStatus,
    ) -> list[StrategyRun]:

        result = await self.db.execute(
            select(StrategyRun)
            .where(
                StrategyRun.status == status
            )
            .order_by(
                StrategyRun.started_at.desc()
            )
        )

        return list(result.scalars().all())

    async def get_by_type(
        self,
        run_type: StrategyRunType,
    ) -> list[StrategyRun]:

        result = await self.db.execute(
            select(StrategyRun)
            .where(
                StrategyRun.run_type == run_type
            )
            .order_by(
                StrategyRun.started_at.desc()
            )
        )

        return list(result.scalars().all())

    async def get_latest(
        self,
    ) -> StrategyRun | None:

        result = await self.db.execute(
            select(StrategyRun)
            .order_by(
                StrategyRun.started_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_all(self) -> list[StrategyRun]:

        result = await self.db.execute(
            select(StrategyRun).order_by(
                StrategyRun.started_at.desc()
            )
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    async def update(
        self,
        strategy_run: StrategyRun,
        **kwargs,
    ) -> StrategyRun:

        for key, value in kwargs.items():
            setattr(strategy_run, key, value)

        await self.db.commit()
        await self.db.refresh(strategy_run)

        return strategy_run

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    async def delete(
        self,
        strategy_run: StrategyRun,
    ) -> None:

        await self.db.delete(strategy_run)
        await self.db.commit()

    # ---------------------------------------------------------
    # Utility
    # ---------------------------------------------------------

    async def exists(
        self,
        strategy_run_id: UUID,
    ) -> bool:

        return (
            await self.get_by_id(strategy_run_id)
        ) is not None