# app/repositories/symbol_repository.py

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.symbol import Symbol


class SymbolRepository:
    """
    Repository responsible for Symbol database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create(self, **data) -> Symbol:
        symbol = Symbol(**data)

        self.db.add(symbol)

        await self.db.commit()
        await self.db.refresh(symbol)

        return symbol

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(self, symbol_id: UUID) -> Symbol | None:
        result = await self.db.execute(
            select(Symbol).where(Symbol.id == symbol_id)
        )

        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Symbol | None:
        result = await self.db.execute(
            select(Symbol).where(Symbol.name == name)
        )

        return result.scalar_one_or_none()

    async def get_all(self) -> list[Symbol]:
        result = await self.db.execute(
            select(Symbol).order_by(Symbol.name)
        )

        return result.scalars().all()

    async def get_active(self) -> list[Symbol]:
        result = await self.db.execute(
            select(Symbol)
            .where(Symbol.active.is_(True))
            .order_by(Symbol.name)
        )

        return result.scalars().all()

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update(
        self,
        symbol: Symbol,
        **data,
    ) -> Symbol:

        for field, value in data.items():
            setattr(symbol, field, value)

        await self.db.commit()
        await self.db.refresh(symbol)

        return symbol

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete(self, symbol: Symbol) -> None:
        await self.db.delete(symbol)
        await self.db.commit()