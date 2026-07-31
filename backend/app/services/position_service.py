from uuid import UUID

from app.core.constants import PositionStatus
from app.repositories.position_repository import PositionRepository
from app.schemas.position import PositionCreate, PositionUpdate


class PositionService:
    def __init__(self, repository: PositionRepository):
        self.repository = repository

    async def create_position(self, data: PositionCreate):
        existing = await self.repository.get_by_ticket(data.ticket)
        if existing:
            raise ValueError("Position with this ticket already exists")

        return await self.repository.create(**data.model_dump())

    async def get_position(self, position_id: UUID):
        position = await self.repository.get_by_id(position_id)
        if not position:
            raise ValueError("Position not found")
        return position

    async def get_positions(self):
        return await self.repository.get_all()

    async def get_account_positions(self, account_id: UUID):
        return await self.repository.get_by_account(account_id)

    async def get_symbol_positions(self, symbol_id: UUID):
        return await self.repository.get_by_symbol(symbol_id)

    async def get_status_positions(self, status: PositionStatus):
        return await self.repository.get_by_status(status)

    async def get_open_positions(self):
        return await self.repository.get_open_positions()

    async def update_position(self, position_id: UUID, data: PositionUpdate):
        position = await self.get_position(position_id)

        if position.status == PositionStatus.CLOSED:
            raise ValueError("Closed positions cannot be modified")

        return await self.repository.update(
            position,
            **data.model_dump(exclude_unset=True),
        )

    async def update_position_status(
        self,
        position_id: UUID,
        status: PositionStatus,
    ):
        position = await self.get_position(position_id)
        return await self.repository.update_status(position, status)

    async def delete_position(self, position_id: UUID):
        position = await self.get_position(position_id)
        if position.status == PositionStatus.OPEN:
            raise ValueError("Open positions cannot be deleted")
        await self.repository.delete(position)
