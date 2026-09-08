from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.symbol import Symbol


class SymbolRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        symbol_id: UUID,
    ) -> Symbol | None:

        result = await self.db.execute(
            select(Symbol).where(
                Symbol.id == symbol_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
    ) -> Symbol | None:

        result = await self.db.execute(
            select(Symbol).where(
                Symbol.name == name,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name_excluding(
        self,
        name: str,
        symbol_id: UUID,
    ) -> Symbol | None:

        result = await self.db.execute(
            select(Symbol).where(
                Symbol.name == name,
                Symbol.id != symbol_id,
            )
        )

        return result.scalar_one_or_none()

    async def list_all(
        self,
    ) -> list[Symbol]:

        result = await self.db.execute(select(Symbol).order_by(Symbol.name.asc()))

        return list(result.scalars().all())

    async def list_active(
        self,
    ) -> list[Symbol]:

        result = await self.db.execute(
            select(Symbol)
            .where(
                Symbol.active.is_(True),
            )
            .order_by(Symbol.name.asc())
        )

        return list(result.scalars().all())

    def add(
        self,
        symbol: Symbol,
    ) -> Symbol:

        self.db.add(symbol)

        return symbol

    def update(
        self,
        symbol: Symbol,
    ) -> Symbol:

        self.db.add(symbol)

        return symbol

    async def delete(
        self,
        symbol: Symbol,
    ) -> None:

        await self.db.delete(symbol)

    async def commit(self) -> None:

        await self.db.commit()

    async def refresh(
        self,
        symbol: Symbol,
    ) -> Symbol:

        await self.db.refresh(symbol)

        return symbol

    async def flush(self) -> None:

        await self.db.flush()

    async def rollback(self) -> None:

        await self.db.rollback()
