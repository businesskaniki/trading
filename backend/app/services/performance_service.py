from uuid import UUID

from app.core.constants import PerformancePeriod
from app.repositories.performance_repository import PerformanceRepository
from app.schemas.performance import (
    PerformanceCreate,
    PerformanceUpdate,
)


class PerformanceService:
    """
    Business logic layer for Performance.
    """

    def __init__(
        self,
        repository: PerformanceRepository,
    ):
        self.repository = repository


    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create_performance(
        self,
        data: PerformanceCreate,
    ):

        existing = await self.repository.get_by_strategy_run(
            data.strategy_run_id
        )

        if existing:
            raise ValueError(
                "Performance already exists for this strategy run"
            )

        return await self.repository.create(
            **data.model_dump()
        )


    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_performance(
        self,
        performance_id: UUID,
    ):

        performance = await self.repository.get_by_id(
            performance_id
        )

        if not performance:
            raise ValueError(
                "Performance record not found"
            )

        return performance


    async def get_strategy_performance(
        self,
        strategy_run_id: UUID,
    ):

        return await self.repository.get_by_strategy_run(
            strategy_run_id
        )


    async def get_all_performance(self):

        return await self.repository.get_all()


    async def get_by_period(
        self,
        period: PerformancePeriod,
    ):

        return await self.repository.get_by_period(
            period
        )


    async def get_latest(self):

        return await self.repository.get_latest()


    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update_performance(
        self,
        performance_id: UUID,
        data: PerformanceUpdate,
    ):

        performance = await self.get_performance(
            performance_id
        )

        return await self.repository.update(
            performance,
            **data.model_dump(
                exclude_unset=True
            )
        )


    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete_performance(
        self,
        performance_id: UUID,
    ):

        performance = await self.get_performance(
            performance_id
        )

        await self.repository.delete(
            performance
        )