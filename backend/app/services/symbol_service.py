from uuid import UUID

from app.database.models.symbol import Symbol
from app.repositories.symbol_repository import SymbolRepository
from app.schemas.symbol import SymbolCreate, SymbolUpdate


class SymbolService:
    """
    Business logic for canonical trading symbols.

    Symbols are global AQE instruments and are not owned by
    individual users or trading accounts.
    """

    def __init__(self, repository: SymbolRepository):
        self.repository = repository

    def get_symbol(
        self,
        symbol_id: UUID,
    ) -> Symbol:
        symbol = self.repository.get_by_id(symbol_id)

        if symbol is None:
            raise ValueError("Symbol not found.")

        return symbol

    def get_by_name(
        self,
        name: str,
    ) -> Symbol | None:
        return self.repository.get_by_name(name)

    def create_symbol(
        self,
        data: SymbolCreate,
    ) -> Symbol:
        existing = self.repository.get_by_name(data.name)

        if existing is not None:
            raise ValueError(f"Symbol '{data.name}' already exists.")

        symbol = Symbol(
            name=data.name,
            description=data.description,
            asset_class=data.asset_class,
            active=data.active,
        )

        self.repository.add(symbol)
        self.repository.commit()
        self.repository.refresh(symbol)

        return symbol

    def list_symbols(
        self,
        active_only: bool = False,
    ) -> list[Symbol]:
        if active_only:
            return self.repository.list_active()

        return self.repository.list_all()

    def update_symbol(
        self,
        symbol_id: UUID,
        data: SymbolUpdate,
    ) -> Symbol:
        symbol = self.get_symbol(symbol_id)

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if "name" in update_data:
            existing = self.repository.get_by_name_excluding(
                name=update_data["name"],
                symbol_id=symbol_id,
            )

            if existing is not None:
                raise ValueError(f"Symbol '{update_data['name']}' already exists.")

        for field, value in update_data.items():
            setattr(symbol, field, value)

        self.repository.update(symbol)
        self.repository.commit()
        self.repository.refresh(symbol)

        return symbol

    def delete_symbol(
        self,
        symbol_id: UUID,
    ) -> None:
        symbol = self.get_symbol(symbol_id)

        self.repository.delete(symbol)
        self.repository.commit()
