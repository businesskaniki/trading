from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.trading_account import TradingAccount


class TradingAccountRepository:
    """
    Async repository for TradingAccount persistence operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==========================================================
    # GET BY ID
    # ==========================================================

    async def get_by_id(
        self,
        account_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(TradingAccount.id == account_id)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # GET BY ID AND USER
    # ==========================================================

    async def get_by_id_and_user(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(
                TradingAccount.id == account_id,
                TradingAccount.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # GET BY BROKER / SERVER / LOGIN
    # ==========================================================

    async def get_by_identity(
        self,
        broker,
        server: str,
        login: int,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(
                TradingAccount.broker == broker,
                TradingAccount.server == server,
                TradingAccount.login == login,
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # LIST BY USER
    # ==========================================================

    async def list_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.user_id == user_id)
            .order_by(TradingAccount.created_at.desc())
        )

        return list(result.scalars().all())

    # ==========================================================
    # ADD
    # ==========================================================

    def add(
        self,
        account: TradingAccount,
    ) -> TradingAccount:

        self.db.add(account)

        return account

    # ==========================================================
    # UPDATE
    # ==========================================================

    def update(
        self,
        account: TradingAccount,
    ) -> TradingAccount:

        self.db.add(account)

        return account

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        account: TradingAccount,
    ) -> None:

        await self.db.delete(account)

    # ==========================================================
    # COMMIT
    # ==========================================================

    async def commit(self) -> None:

        await self.db.commit()

    # ==========================================================
    # REFRESH
    # ==========================================================

    async def refresh(
        self,
        account: TradingAccount,
    ) -> TradingAccount:

        await self.db.refresh(account)

        return account

    # ==========================================================
    # FLUSH
    # ==========================================================

    async def flush(self) -> None:

        await self.db.flush()

    # ==========================================================
    # ROLLBACK
    # ==========================================================

    async def rollback(self) -> None:

        await self.db.rollback()
