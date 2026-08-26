from datetime import datetime, timezone
from uuid import UUID

from app.core.constants import StrategyRunStatus, StrategyRunType
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.schemas.bot import BotStartRequest, BotStatusResponse
from app.schemas.strategy_run import StrategyRunCreate, StrategyRunUpdate


class BotService:
    def __init__(self, repository: StrategyRunRepository):
        self.repository = repository

    async def status(self, user_id: UUID) -> BotStatusResponse:
        run = await self.repository.get_running_for_user(user_id)
        if run is None:
            run = await self.repository.get_latest_for_user(user_id)
        if run is None:
            return BotStatusResponse(active=False)
        return self._to_status(run)

    async def start(self, user_id: UUID, data: BotStartRequest) -> BotStatusResponse:
        running = await self.repository.get_running_for_user(user_id)
        if running is not None:
            raise ValueError("A bot is already running")

        now = datetime.now(timezone.utc)
        run = await self.repository.create(
            user_id=user_id,
            **StrategyRunCreate(
                strategy_name=data.strategy_name,
                strategy_version=data.strategy_version,
                run_name=f"{data.strategy_name} paper bot",
                run_type=StrategyRunType.PAPER,
                status=StrategyRunStatus.RUNNING,
                parameters={
                    "account_id": str(data.account_id) if data.account_id else None,
                    "risk_percent": str(data.risk_percent),
                    "broker": "paper",
                },
                symbols=data.symbols,
                timeframe=data.timeframe,
                started_at=now,
            ).model_dump(),
        )
        return self._to_status(run)

    async def stop(self, user_id: UUID) -> BotStatusResponse:
        run = await self.repository.get_running_for_user(user_id)
        if run is None:
            return await self.status(user_id)
        run = await self.repository.update(
            run,
            status=StrategyRunStatus.CANCELLED,
            ended_at=datetime.now(timezone.utc),
        )
        return self._to_status(run)

    def _to_status(self, run) -> BotStatusResponse:
        parameters = run.parameters or {}
        account_id = parameters.get("account_id")
        return BotStatusResponse(
            active=run.status == StrategyRunStatus.RUNNING,
            status=run.status,
            run_id=run.id,
            strategy_name=run.strategy_name,
            symbols=run.symbols,
            timeframe=run.timeframe,
            account_id=UUID(account_id) if account_id else None,
            risk_percent=parameters.get("risk_percent"),
            started_at=run.started_at,
            ended_at=run.ended_at,
        )