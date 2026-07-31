from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AccountStatus
from app.core.constants import BrokerType
from app.database.models.trading_account import TradingAccount


class TradingAccountRepository:
    """
    Repository responsible for TradingAccount database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    async def create(self, **kwargs) -> TradingAccount:
        account = TradingAccount(**kwargs)

        self.db.add(account)

        await self.db.commit()
        await self.db.refresh(account)

        return account

    # ---------------------------------------------------------
    # Get
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        account_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(
                TradingAccount.id == account_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_account_number(
        self,
        account_number: int,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(
                TradingAccount.account_number == account_number
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker(
        self,
        broker: BrokerType,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.broker == broker
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: AccountStatus,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.status == status
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_active_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.active.is_(True)
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_demo_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.is_demo.is_(True)
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_live_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.is_demo.is_(False)
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.user_id == user_id
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_by_id_and_user(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.id == account_id,
                TradingAccount.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_active_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.user_id == user_id,
                TradingAccount.active.is_(True),
            )
            .order_by(
                TradingAccount.account_name
            )

        return list(result.scalars().all())

    async def get_demo_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.user_id == user_id,
                TradingAccount.is_demo.is_(True),
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_live_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(
                TradingAccount.user_id == user_id,
                TradingAccount.is_demo.is_(False),
            )
            .order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    async def get_all(self) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount).order_by(
                TradingAccount.account_name
            )
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    async def update(
        self,
        account: TradingAccount,
        **kwargs,
    ) -> TradingAccount:

        for key, value in kwargs.items():
            setattr(account, key, value)

        await self.db.commit()
        await self.db.refresh(account)

        return account

    async def update_balance(
        self,
        account: TradingAccount,
        *,
        balance,
        equity,
        margin,
        free_margin,
        margin_level,
    ) -> TradingAccount:

        account.balance = balance
        account.equity = equity
        account.margin = margin
        account.free_margin = free_margin
        account.margin_level = margin_level

        await self.db.commit()
        await self.db.refresh(account)

        return account

    async def update_status(
        self,
        account: TradingAccount,
        status: AccountStatus,
    ) -> TradingAccount:

        account.status = status

        await self.db.commit()
        await self.db.refresh(account)

        return account

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    async def delete(
        self,
        account: TradingAccount,
    ) -> None:

        await self.db.delete(account)
        await self.db.commit()

    # ---------------------------------------------------------
    # Utility
    # ---------------------------------------------------------

    async def exists(
        self,
        account_id: UUID,
    ) -> bool:

        return (
            await self.get_by_id(account_id)
        ) is not None