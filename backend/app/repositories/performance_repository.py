# app/repositories/performance_repository.py

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import PerformancePeriod
from app.database.models.performance import Performance


class PerformanceRepository:
    """
    Repository responsible for Performance database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create(self, **data) -> Performance:
        performance = Performance(**data)

        self.db.add(performance)

        await self.db.commit()
        await self.db.refresh(performance)

        return performance

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        performance_id: UUID,
    ) -> Performance | None:

        result = await self.db.execute(
            select(Performance).options(selectinload(Performance.strategy_run))
            .options(
                selectinload(Performance.strategy_run),
            )
            .where(Performance.id == performance_id)
        )

        return result.scalar_one_or_none()

    async def get_by_strategy_run(
        self,
        strategy_run_id: UUID,
    ) -> Performance | None:

        result = await self.db.execute(
            select(Performance).options(selectinload(Performance.strategy_run))
            .where(
                Performance.strategy_run_id == strategy_run_id
            )
        )

        return result.scalar_one_or_none()

    async def get_all(self) -> list[Performance]:

        result = await self.db.execute(
            select(Performance).options(selectinload(Performance.strategy_run))
            .options(
                selectinload(Performance.strategy_run),
            )
            .order_by(
                Performance.generated_at.desc()
            )
        )

        return result.scalars().all()

    async def get_by_period(
        self,
        period: PerformancePeriod,
    ) -> list[Performance]:

        result = await self.db.execute(
            select(Performance).options(selectinload(Performance.strategy_run))
            .where(
                Performance.period == period
            )
            .order_by(
                Performance.generated_at.desc()
            )
        )

        return result.scalars().all()

    async def get_latest(self) -> Performance | None:

        result = await self.db.execute(
            select(Performance).options(selectinload(Performance.strategy_run))
            .order_by(
                Performance.generated_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update(
        self,
        performance: Performance,
        **data,
    ) -> Performance:

        for field, value in data.items():
            setattr(performance, field, value)

        await self.db.commit()
        await self.db.refresh(performance)

        return performance

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete(
        self,
        performance: Performance,
    ) -> None:

        await self.db.delete(performance)
        await self.db.commit()