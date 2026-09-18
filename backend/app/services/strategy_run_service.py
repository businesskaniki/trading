from uuid import UUID

from app.core.constants import StrategyRunStatus, StrategyRunType
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.schemas.strategy_run import (
    StrategyRunCreate,
    StrategyRunUpdate,
)


class StrategyRunService:
    """
    Business logic layer for Strategy Runs.
    """

    def __init__(
        self,
        repository: StrategyRunRepository,
    ):
        self.repository = repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_strategy_run(
        self,
        data: StrategyRunCreate,
        user_id: UUID,
    ):
        """
        Create a Strategy Run owned by the authenticated user.
        """

        return await self.repository.create(
            user_id=user_id,
            **data.model_dump(),
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_strategy_run(
        self,
        strategy_run_id: UUID,
        user_id: UUID | None = None,
    ):

        strategy_run = await self.repository.get_by_id(
            strategy_run_id,
            user_id=user_id,
        )

        if not strategy_run:
            raise ValueError(
                "Strategy run not found"
            )

        return strategy_run

    async def get_strategy_runs(
        self,
        user_id: UUID | None = None,
    ):

        return await self.repository.get_all(user_id=user_id)

    async def get_by_name(
        self,
        strategy_name: str,
        user_id: UUID | None = None,
    ):

        runs = await self.repository.get_by_name(strategy_name)
        return [run for run in runs if user_id is None or run.user_id == user_id]

    async def get_by_status(
        self,
        status: StrategyRunStatus,
        user_id: UUID | None = None,
    ):

        runs = await self.repository.get_by_status(status)
        return [run for run in runs if user_id is None or run.user_id == user_id]

    async def get_by_type(
        self,
        run_type: StrategyRunType,
        user_id: UUID | None = None,
    ):

        runs = await self.repository.get_by_type(run_type)
        return [run for run in runs if user_id is None or run.user_id == user_id]

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_strategy_run(
        self,
        strategy_run_id: UUID,
        data: StrategyRunUpdate,
        user_id: UUID | None = None,
    ):

        strategy_run = await self.get_strategy_run(
            strategy_run_id,
            user_id=user_id,
        )

        return await self.repository.update(
            strategy_run,
            **data.model_dump(
                exclude_unset=True
            ),
        )

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_strategy_run(
        self,
        strategy_run_id: UUID,
        user_id: UUID | None = None,
    ):

        strategy_run = await self.get_strategy_run(
            strategy_run_id,
            user_id=user_id,
        )

        await self.repository.delete(
            strategy_run
        )