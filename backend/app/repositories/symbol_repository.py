from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.symbol import Symbol


class SymbolRepository:
    """
    Repository responsible for Symbol database operations.

    This repository only handles database persistence.
    Risk calculations and business rules belong in the service layer.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================
    # CREATE
    # =========================================================

    async def create(
        self,
        **data,
    ) -> Symbol:

        symbol = Symbol(**data)

        self.db.add(symbol)

        await self.db.commit()
        await self.db.refresh(symbol)

        return symbol

    # =========================================================
    # READ
    # =========================================================

    async def get_by_id(
        self,
        symbol_id: UUID,
    ) -> Symbol | None:

        result = await self.db.execute(select(Symbol).where(Symbol.id == symbol_id))

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET ACTIVE BY ID
    # ---------------------------------------------------------

    async def get_active_by_id(
        self,
        symbol_id: UUID,
    ) -> Symbol | None:

        result = await self.db.execute(
            select(Symbol).where(
                Symbol.id == symbol_id,
                Symbol.active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET BY NAME
    # ---------------------------------------------------------

    async def get_by_name(
        self,
        name: str,
    ) -> Symbol | None:

        result = await self.db.execute(select(Symbol).where(Symbol.name == name))

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET ACTIVE BY NAME
    # ---------------------------------------------------------

    async def get_active_by_name(
        self,
        name: str,
    ) -> Symbol | None:

        result = await self.db.execute(
            select(Symbol).where(
                Symbol.name == name,
                Symbol.active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET ALL
    # ---------------------------------------------------------

    async def get_all(
        self,
    ) -> list[Symbol]:

        result = await self.db.execute(select(Symbol).order_by(Symbol.name))

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET ACTIVE
    # ---------------------------------------------------------

    async def get_active(
        self,
    ) -> list[Symbol]:

        result = await self.db.execute(
            select(Symbol).where(Symbol.active.is_(True)).order_by(Symbol.name)
        )

        return list(result.scalars().all())

    # =========================================================
    # UPDATE
    # =========================================================

    async def update(
        self,
        symbol: Symbol,
        **data,
    ) -> Symbol:

        for field, value in data.items():
            setattr(
                symbol,
                field,
                value,
            )

        await self.db.commit()
        await self.db.refresh(symbol)

        return symbol

    # =========================================================
    # DELETE
    # =========================================================

    async def delete(
        self,
        symbol: Symbol,
    ) -> None:

        await self.db.delete(symbol)
        await self.db.commit()

    # =========================================================
    # UTILITY
    # =========================================================

    async def exists(
        self,
        symbol_id: UUID,
    ) -> bool:

        result = await self.db.execute(select(Symbol.id).where(Symbol.id == symbol_id))

        return result.scalar_one_or_none() is not None

    # ---------------------------------------------------------
    # CHECK ACTIVE
    # ---------------------------------------------------------

    async def is_active(
        self,
        symbol_id: UUID,
    ) -> bool:

        result = await self.db.execute(
            select(Symbol.id).where(
                Symbol.id == symbol_id,
                Symbol.active.is_(True),
            )
        )

        return result.scalar_one_or_none() is not None
