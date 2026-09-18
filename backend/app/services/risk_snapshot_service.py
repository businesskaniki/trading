from uuid import UUID

from app.repositories.snapshot_repository import RiskSnapshotRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.snapshot import RiskSnapshotCreate, RiskSnapshotUpdate


class RiskSnapshotService:
    def __init__(self, repository: RiskSnapshotRepository, account_repository: TradingAccountRepository | None = None):
        self.repository = repository
        self.account_repository = account_repository

    async def create_snapshot(self, data: RiskSnapshotCreate, user_id: UUID | None = None):
        if user_id is not None and self.account_repository is not None:
            if await self.account_repository.get_by_id_and_user(data.account_id, user_id) is None:
                raise ValueError("Trading account not found")
        return await self.repository.create(**data.model_dump())

    async def get_snapshot(self, snapshot_id: UUID, user_id: UUID | None = None):
        snapshot = await self.repository.get_by_id(snapshot_id)
        if not snapshot:
            raise ValueError("Risk snapshot not found")
        if user_id is not None and snapshot.account.user_id != user_id:
            raise ValueError("Risk snapshot not found")
        return snapshot

    async def get_account_snapshots(self, account_id: UUID):
        return await self.repository.get_by_account(account_id)

    async def get_snapshots(self, user_id: UUID | None = None):
        snapshots = await self.repository.get_all()
        if user_id is not None:
            return [snapshot for snapshot in snapshots if snapshot.account.user_id == user_id]
        return snapshots

    async def update_snapshot(self, snapshot_id: UUID, data: RiskSnapshotUpdate, user_id: UUID | None = None):
        snapshot = await self.get_snapshot(snapshot_id, user_id=user_id)
        return await self.repository.update(
            snapshot,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_snapshot(self, snapshot_id: UUID, user_id: UUID | None = None):
        snapshot = await self.get_snapshot(snapshot_id, user_id=user_id)
        await self.repository.delete(snapshot)
