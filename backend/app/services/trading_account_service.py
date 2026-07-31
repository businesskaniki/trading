from decimal import Decimal
from uuid import UUID

from app.core.constants import AccountStatus
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.trading_account import TradingAccountCreate, TradingAccountUpdate


class TradingAccountService:
    def __init__(self, repository: TradingAccountRepository):
        self.repository = repository

    async def create_account(self, data: TradingAccountCreate, user_id: UUID):
        existing = await self.repository.get_by_account_number(
            data.account_number
        )
        if existing:
            raise ValueError("Trading account with this number already exists")

        return await self.repository.create(
            **data.model_dump(),
            user_id=user_id,
        )

    async def get_account(self, account_id: UUID, user_id: UUID):
        account = await self.repository.get_by_id_and_user(
            account_id,
            user_id,
        )
        if not account:
            raise ValueError("Trading account not found")
        return account

    async def get_accounts(self, user_id: UUID):
        return await self.repository.get_by_user(user_id)

    async def get_active_accounts(self, user_id: UUID):
        return await self.repository.get_active_by_user(user_id)

    async def get_demo_accounts(self, user_id: UUID):
        return await self.repository.get_demo_by_user(user_id)

    async def get_live_accounts(self, user_id: UUID):
        return await self.repository.get_live_by_user(user_id)

    async def update_account(self, account_id: UUID, data: TradingAccountUpdate, user_id: UUID):
        account = await self.get_account(account_id, user_id)
        return await self.repository.update(
            account,
            **data.model_dump(exclude_unset=True),
        )

    async def update_balance(
        self,
        account_id: UUID,
        balance: Decimal,
        equity: Decimal,
        margin: Decimal,
        free_margin: Decimal,
        margin_level: Decimal,
        user_id: UUID,
    ):
        account = await self.get_account(account_id, user_id)
        return await self.repository.update_balance(
            account,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
        )

    async def set_status(self, account_id: UUID, status: AccountStatus, user_id: UUID):
        account = await self.get_account(account_id, user_id)
        return await self.repository.update_status(account, status)

    async def delete_account(self, account_id: UUID, user_id: UUID):
        account = await self.get_account(account_id, user_id)
        if account.status == AccountStatus.ARCHIVED:
            raise ValueError("Archived accounts cannot be deleted")
        await self.repository.delete(account)
