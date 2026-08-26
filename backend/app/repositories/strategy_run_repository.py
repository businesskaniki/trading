from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.models.strategy_run import StrategyRun


class StrategyRunRepository:
    """
    Repository responsible for StrategyRun database operations.
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
    ) -> StrategyRun:

        strategy_run = StrategyRun(
            **data
        )

        self.db.add(strategy_run)

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_run
        )

        return strategy_run

    # ==========================================================
    # READ
    # ==========================================================

    async def get_by_id(
        self,
        strategy_run_id: UUID,
    ) -> StrategyRun | None:

        result = await self.db.execute(
            select(StrategyRun)
            .where(
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

        return list(
            result.scalars().all()
        )

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

        return list(
            result.scalars().all()
        )

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

        return list(
            result.scalars().all()
        )

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

    async def get_latest_for_user(
        self,
        user_id: UUID,
    ) -> StrategyRun | None:
        result = await self.db.execute(
            select(StrategyRun)
            .where(StrategyRun.user_id == user_id)
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_running_for_user(
        self,
        user_id: UUID,
    ) -> StrategyRun | None:
        result = await self.db.execute(
            select(StrategyRun)
            .where(
                StrategyRun.user_id == user_id,
                StrategyRun.status == StrategyRunStatus.RUNNING,
            )
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[StrategyRun]:

        result = await self.db.execute(
            select(StrategyRun)
            .order_by(
                StrategyRun.started_at.desc()
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update(
        self,
        strategy_run: StrategyRun,
        commit: bool = True,
        **data,
    ) -> StrategyRun:

        for field, value in data.items():
            setattr(
                strategy_run,
                field,
                value,
            )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_run
        )

        return strategy_run

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        strategy_run: StrategyRun,
        commit: bool = True,
    ) -> None:

        await self.db.delete(
            strategy_run
        )

        await self.db.flush()

        if commit:
            await self.db.commit()

    # ==========================================================
    # UTILITY
    # ==========================================================

    async def exists(
        self,
        strategy_run_id: UUID,
    ) -> bool:

        return (
            await self.get_by_id(
                strategy_run_id
            )
        ) is not None