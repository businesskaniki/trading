from uuid import uuid4
import os
import asyncio


for key, value in {
    "SECRET_KEY": "test-secret",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_DB": "test",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "REDIS_HOST": "localhost",
    "SMTP_HOST": "localhost",
    "SMTP_USERNAME": "test",
    "SMTP_PASSWORD": "test",
    "SMTP_FROM_EMAIL": "test@example.com",
}.items():
    os.environ.setdefault(key, value)

from app.core.constants import StrategyRunStatus
from app.schemas.bot import BotStartRequest
from app.services.bot_service import BotService


class FakeRepository:
    def __init__(self):
        self.run = None
        self.created = None

    async def get_running_for_user(self, user_id):
        if self.run and self.run.status == StrategyRunStatus.RUNNING:
            return self.run
        return None

    async def get_latest_for_user(self, user_id):
        return self.run

    async def create(self, **data):
        self.created = data
        self.run = type("Run", (), data)()
        self.run.id = uuid4()
        self.run.created_at = self.run.started_at
        self.run.updated_at = self.run.started_at
        return self.run

    async def update(self, run, **data):
        for key, value in data.items():
            setattr(run, key, value)
        return run


def test_start_persists_risk_and_strategy_configuration():
    async def run():
        repository = FakeRepository()
        service = BotService(repository)
        account_id = uuid4()

        result = await service.start(
            uuid4(),
            BotStartRequest(
                strategy_name="ema_cross",
                symbols=["EURUSD"],
                timeframe="M1",
                account_id=account_id,
                risk_percent="0.5",
            ),
        )

        assert result.active is True
        assert repository.created["status"] == StrategyRunStatus.RUNNING
        assert repository.created["run_type"].value == "PAPER"
        assert repository.created["parameters"]["account_id"] == str(account_id)
        assert repository.created["parameters"]["risk_percent"] == "0.5"
        assert repository.created["symbols"] == ["EURUSD"]

    asyncio.run(run())


def test_stop_persists_cancelled_state():
    async def run():
        repository = FakeRepository()
        service = BotService(repository)
        user_id = uuid4()

        await service.start(
            user_id,
            BotStartRequest(strategy_name="ema_cross", symbols=["EURUSD"]),
        )
        result = await service.stop(user_id)

        assert result.active is False
        assert result.status == StrategyRunStatus.CANCELLED
        assert result.ended_at is not None

    asyncio.run(run())