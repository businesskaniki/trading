from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.risk_snapshot import RiskSnapshot


class RiskSnapshotRepository:
    """
    Repository responsible for RiskSnapshot database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **data) -> RiskSnapshot:
        snapshot = RiskSnapshot(**data)

        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)

        return snapshot

    async def get_by_id(self, snapshot_id: UUID) -> RiskSnapshot | None:
        result = await self.db.execute(
            select(RiskSnapshot).where(RiskSnapshot.id == snapshot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_account(self, account_id: UUID) -> list[RiskSnapshot]:
        result = await self.db.execute(
            select(RiskSnapshot)
            .where(RiskSnapshot.account_id == account_id)
            .order_by(RiskSnapshot.snapshot_time.desc())
        )
        return result.scalars().all()

    async def get_all(self) -> list[RiskSnapshot]:
        result = await self.db.execute(
            select(RiskSnapshot).order_by(RiskSnapshot.snapshot_time.desc()))
        return result.scalars().all()

    async def update(self, snapshot: RiskSnapshot, **data) -> RiskSnapshot:
        for field, value in data.items():
            setattr(snapshot, field, value)

        await self.db.commit()
        await self.db.refresh(snapshot)

        return snapshot

    async def delete(self, snapshot: RiskSnapshot) -> None:
        await self.db.delete(snapshot)
        await self.db.commit()
