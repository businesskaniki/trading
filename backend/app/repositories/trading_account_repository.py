from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AccountStatus
from app.core.constants import BrokerType
from app.database.models.trading_account import TradingAccount


class TradingAccountRepository:
    """
    Repository responsible for TradingAccount database operations.

    This repository only handles persistence and database queries.
    Business logic belongs in the service layer.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================
    # CREATE
    # =========================================================

    async def create(
        self,
        **kwargs,
    ) -> TradingAccount:

        account = TradingAccount(**kwargs)

        self.db.add(account)

        await self.db.commit()
        await self.db.refresh(account)

        return account

    # =========================================================
    # GET
    # =========================================================

    async def get_by_id(
        self,
        account_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(TradingAccount.id == account_id)
        )

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET ACTIVE BY ID
    # ---------------------------------------------------------

    async def get_active_by_id(
        self,
        account_id: UUID,
    ) -> TradingAccount | None:

        result = await self.db.execute(
            select(TradingAccount).where(
                TradingAccount.id == account_id,
                TradingAccount.active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    # ---------------------------------------------------------
    # GET BY ACCOUNT NUMBER
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # GET BY BROKER
    # ---------------------------------------------------------

    async def get_by_broker(
        self,
        broker: BrokerType,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.broker == broker)
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET BY STATUS
    # ---------------------------------------------------------

    async def get_by_status(
        self,
        status: AccountStatus,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.status == status)
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET ACTIVE ACCOUNTS
    # ---------------------------------------------------------

    async def get_active_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.active.is_(True))
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET DEMO ACCOUNTS
    # ---------------------------------------------------------

    async def get_demo_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.is_demo.is_(True))
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET LIVE ACCOUNTS
    # ---------------------------------------------------------

    async def get_live_accounts(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.is_demo.is_(False))
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET BY USER
    # ---------------------------------------------------------

    async def get_by_user(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount)
            .where(TradingAccount.user_id == user_id)
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET BY ID AND USER
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # GET ACTIVE BY USER
    # ---------------------------------------------------------

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
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET DEMO BY USER
    # ---------------------------------------------------------

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
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET LIVE BY USER
    # ---------------------------------------------------------

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
            .order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # GET ALL
    # ---------------------------------------------------------

    async def get_all(
        self,
    ) -> list[TradingAccount]:

        result = await self.db.execute(
            select(TradingAccount).order_by(TradingAccount.account_name)
        )

        return list(result.scalars().all())

    # =========================================================
    # UPDATE
    # =========================================================

    async def update(
        self,
        account: TradingAccount,
        **kwargs,
    ) -> TradingAccount:

        for key, value in kwargs.items():
            setattr(
                account,
                key,
                value,
            )

        await self.db.commit()
        await self.db.refresh(account)

        return account

    # ---------------------------------------------------------
    # UPDATE BALANCE
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # UPDATE STATUS
    # ---------------------------------------------------------

    async def update_status(
        self,
        account: TradingAccount,
        status: AccountStatus,
    ) -> TradingAccount:

        account.status = status

        await self.db.commit()
        await self.db.refresh(account)

        return account

    # =========================================================
    # DELETE
    # =========================================================

    async def delete(
        self,
        account: TradingAccount,
    ) -> None:

        await self.db.delete(account)
        await self.db.commit()

    # =========================================================
    # UTILITY
    # =========================================================

    async def exists(
        self,
        account_id: UUID,
    ) -> bool:

        result = await self.db.execute(
            select(TradingAccount.id).where(TradingAccount.id == account_id)
        )

        return result.scalar_one_or_none() is not None

    # ---------------------------------------------------------
    # CHECK ACTIVE
    # ---------------------------------------------------------

    async def is_active(
        self,
        account_id: UUID,
    ) -> bool:

        result = await self.db.execute(
            select(TradingAccount.id).where(
                TradingAccount.id == account_id,
                TradingAccount.active.is_(True),
            )
        )

        return result.scalar_one_or_none() is not None
