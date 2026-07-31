from uuid import UUID

from app.repositories.strategy_run_repository import StrategyRunRepository
from app.schemas.strategy_run import StrategyRunCreate, StrategyRunUpdate


class StrategyRunService:
    def __init__(self, repository: StrategyRunRepository):
        self.repository = repository

    async def create_strategy_run(self, data: StrategyRunCreate):
        return await self.repository.create(**data.model_dump())

    async def get_strategy_run(self, strategy_run_id: UUID):
        run = await self.repository.get_by_id(strategy_run_id)
        if not run:
            raise ValueError("Strategy run not found")
        return run

    async def get_strategy_runs(self):
        return await self.repository.get_all()

    async def get_by_name(self, strategy_name: str):
        return await self.repository.get_by_name(strategy_name)

    async def get_by_status(self, status):
        return await self.repository.get_by_status(status)

    async def get_by_type(self, run_type):
        return await self.repository.get_by_type(run_type)

    async def get_latest_strategy_run(self):
        return await self.repository.get_latest()

    async def update_strategy_run(self, strategy_run_id: UUID, data: StrategyRunUpdate):
        run = await self.get_strategy_run(strategy_run_id)
        return await self.repository.update(
            run,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_strategy_run(self, strategy_run_id: UUID):
        run = await self.get_strategy_run(strategy_run_id)
        await self.repository.delete(run)
