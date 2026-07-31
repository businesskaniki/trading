from uuid import UUID

from app.repositories.symbol_repository import SymbolRepository
from app.schemas.symbol import SymbolCreate, SymbolUpdate


class SymbolService:
    def __init__(self, repository: SymbolRepository):
        self.repository = repository

    async def create_symbol(self, data: SymbolCreate):
        existing = await self.repository.get_by_name(data.name)
        if existing:
            raise ValueError("Symbol with this name already exists")

        return await self.repository.create(**data.model_dump())

    async def get_symbol(self, symbol_id: UUID):
        symbol = await self.repository.get_by_id(symbol_id)
        if not symbol:
            raise ValueError("Symbol not found")
        return symbol

    async def get_symbols(self):
        return await self.repository.get_all()

    async def get_active_symbols(self):
        return await self.repository.get_active()

    async def update_symbol(self, symbol_id: UUID, data: SymbolUpdate):
        symbol = await self.get_symbol(symbol_id)
        return await self.repository.update(
            symbol,
            **data.model_dump(exclude_unset=True),
        )

    async def delete_symbol(self, symbol_id: UUID):
        symbol = await self.get_symbol(symbol_id)
        await self.repository.delete(symbol)
