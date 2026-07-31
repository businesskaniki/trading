# app/repositories/position_repository.py

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import PositionStatus
from app.database.models.position import Position


class PositionRepository:
    """
    Repository responsible for Position database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create(self, **data) -> Position:
        position = Position(**data)

        self.db.add(position)

        await self.db.commit()
        await self.db.refresh(position)

        return position

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        position_id: UUID,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
                selectinload(Position.trade),
            )
            .where(Position.id == position_id)
        )

        return result.scalar_one_or_none()

    async def get_by_ticket(
        self,
        ticket: int,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position)
            .where(Position.ticket == ticket)
        )

        return result.scalar_one_or_none()

    async def get_by_order(
        self,
        order_id: UUID,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position)
            .where(Position.order_id == order_id)
        )

        return result.scalar_one_or_none()

    async def get_by_account(
        self,
        account_id: UUID,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .where(Position.account_id == account_id)
            .order_by(Position.opened_at.desc())
        )

        return result.scalars().all()

    async def get_by_symbol(
        self,
        symbol_id: UUID,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .where(Position.symbol_id == symbol_id)
            .order_by(Position.opened_at.desc())
        )

        return result.scalars().all()

    async def get_by_status(
        self,
        status: PositionStatus,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .where(Position.status == status)
            .order_by(Position.opened_at.desc())
        )

        return result.scalars().all()

    async def get_open_positions(self) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .where(Position.status == PositionStatus.OPEN)
            .order_by(Position.opened_at.desc())
        )

        return result.scalars().all()

    async def get_all(self) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
                selectinload(Position.trade),
            )
            .order_by(Position.opened_at.desc())
        )

        return result.scalars().all()

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update(
        self,
        position: Position,
        **data,
    ) -> Position:

        for field, value in data.items():
            setattr(position, field, value)

        await self.db.commit()
        await self.db.refresh(position)

        return position

    async def update_status(
        self,
        position: Position,
        status: PositionStatus,
    ) -> Position:

        position.status = status

        await self.db.commit()
        await self.db.refresh(position)

        return position

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete(
        self,
        position: Position,
    ) -> None:

        await self.db.delete(position)
        await self.db.commit()