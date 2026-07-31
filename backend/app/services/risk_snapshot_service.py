from uuid import UUID

from app.repositories.snapshot_repository import RiskSnapshotRepository
from app.schemas.snapshot import RiskSnapshotCreate, RiskSnapshotUpdate


class RiskSnapshotService:
    def __init__(self, repository: RiskSnapshotRepository):
        self.repository = repository

    async def create_snapshot(self, data: RiskSnapshotCreate):
        return await self.repository.create(**data.model_dump())

    async def get_snapshot(self, snapshot_id: UUID):
        snapshot = await self.repository.get_by_id(snapshot_id)
        if not snapshot:
            raise ValueError("Risk snapshot not found")
        return snapshot

    async def get_account_snapshots(self, account_id: UUID):
        return await self.repository.get_by_account(account_id)

    async def get_snapshots(self):
        return await self.repository.get_all()

    async def update_snapshot(self, snapshot_id: UUID, data: RiskSnapshotUpdate):
        snapshot = await self.get_snapshot(snapshot_id)
        return await self.repository.update(
            snapshot,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_snapshot(self, snapshot_id: UUID):
        snapshot = await self.get_snapshot(snapshot_id)
        await self.repository.delete(snapshot)
