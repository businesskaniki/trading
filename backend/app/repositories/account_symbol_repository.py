from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app.database.models.account_symbol import AccountSymbol
from app.database.models.symbol import Symbol
from app.database.models.trading_account import TradingAccount


class AccountSymbolRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ======================================================================
    # LOADER OPTIONS
    # ======================================================================

    @staticmethod
    def _symbol_load():
        """Load the canonical Symbol required by AccountSymbol responses, while

        explicitly preventing SQLAlchemy from loading the Symbol's large reverse
        relationships.

        This is important for async SQLAlchemy because accidental lazy
        loading during Pydantic serialization can cause
        MissingGreenlet.
        """
        return selectinload(AccountSymbol.symbol).options(
            noload(Symbol.account_symbols),
            noload(Symbol.orders),
            noload(Symbol.positions),
            noload(Symbol.trades),
        )

    # ======================================================================
    # GET
    # ======================================================================

    async def get_by_id(
        self,
        account_symbol_id: UUID,
    ) -> AccountSymbol | None:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.id == account_symbol_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self,
        account_symbol_id: UUID,
        user_id: UUID,
    ) -> AccountSymbol | None:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .join(
                TradingAccount,
                AccountSymbol.account_id == TradingAccount.id,
            )
            .where(
                AccountSymbol.id == account_symbol_id,
                TradingAccount.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_account_and_symbol(
        self,
        account_id: UUID,
        symbol_id: UUID,
    ) -> AccountSymbol | None:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.symbol_id == symbol_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker_symbol(
        self,
        account_id: UUID,
        broker_symbol: str,
    ) -> AccountSymbol | None:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.broker_symbol == broker_symbol,
            )
        )

        return result.scalar_one_or_none()

    # ======================================================================
    # LIST
    # ======================================================================

    async def list_by_account(
        self,
        account_id: UUID,
    ) -> list[AccountSymbol]:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.account_id == account_id,
            )
            .order_by(
                AccountSymbol.broker_symbol.asc(),
            )
        )

        return list(result.scalars().all())

    async def list_enabled_by_account(
        self,
        account_id: UUID,
    ) -> list[AccountSymbol]:
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.enabled.is_(True),
            )
            .order_by(
                AccountSymbol.broker_symbol.asc(),
            )
        )

        return list(result.scalars().all())

    async def list_all_enabled(
        self,
    ) -> list[AccountSymbol]:
        """Return all enabled AccountSymbols across all trading accounts.

        This is used by the global market-data subscription manager
        to determine which broker symbols are currently required by
        AQE.
        """

        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.enabled.is_(True),
            )
            .order_by(
                AccountSymbol.broker_symbol.asc(),
            )
        )

        return list(result.scalars().all())

    async def list_by_account_and_ids(
        self,
        account_id: UUID,
        account_symbol_ids: list[UUID],
    ) -> list[AccountSymbol]:
        if not account_symbol_ids:
            return []

        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.account_id == account_id,
                AccountSymbol.id.in_(account_symbol_ids),
            )
        )

        return list(result.scalars().all())

    # ======================================================================
    # COUNT
    # ======================================================================

    async def count_by_account(
        self,
        account_id: UUID,
    ) -> int:
        result = await self.db.execute(
            select(func.count(AccountSymbol.id)).where(
                AccountSymbol.account_id == account_id,
            )
        )

        return int(result.scalar_one())

    # ======================================================================
    # WRITE
    # ======================================================================

    def add(
        self,
        account_symbol: AccountSymbol,
    ) -> AccountSymbol:
        self.db.add(account_symbol)

        return account_symbol

    def add_many(
        self,
        account_symbols: list[AccountSymbol],
    ) -> list[AccountSymbol]:
        self.db.add_all(account_symbols)

        return account_symbols

    def update(
        self,
        account_symbol: AccountSymbol,
    ) -> AccountSymbol:
        self.db.add(account_symbol)

        return account_symbol

    async def delete(
        self,
        account_symbol: AccountSymbol,
    ) -> None:
        await self.db.delete(account_symbol)

    # ======================================================================
    # TRANSACTION
    # ======================================================================

    async def commit(self) -> None:
        await self.db.commit()

    async def refresh(
        self,
        account_symbol: AccountSymbol,
    ) -> AccountSymbol:
        await self.db.refresh(account_symbol)

        # refresh() does not guarantee that the relationship required by
        # AccountSymbolResponse is loaded, so explicitly reload it.
        result = await self.db.execute(
            select(AccountSymbol)
            .options(self._symbol_load())
            .where(
                AccountSymbol.id == account_symbol.id,
            )
        )

        refreshed = result.scalar_one()

        return refreshed

    async def flush(self) -> None:
        await self.db.flush()

    async def rollback(self) -> None:
        await self.db.rollback()