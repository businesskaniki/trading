from __future__ import annotations

from uuid import UUID

from app.core.security import decrypt_secret, encrypt_secret
from app.database.models.trading_account import TradingAccount
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.schemas.trading_account import (
    TradingAccountCreate,
    TradingAccountStateUpdate,
    TradingAccountUpdate,
)
from app.core.constants import AccountStatus

class TradingAccountService:
    """
    Business logic for managing user trading accounts.

    Broker credentials are encrypted before persistence and
    decrypted only when required for broker communication.
    """

    def __init__(
        self,
        repository: TradingAccountRepository,
    ):
        self.repository = repository

    async def get_owned_account(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> TradingAccount:
        """
        Retrieve a trading account owned by the authenticated user.
        """

        account = await self.repository.get_by_id_and_user(
            account_id=account_id,
            user_id=user_id,
        )

        if account is None:
            raise ValueError("Trading account not found.")

        return account

    async def create_account(
        self,
        user_id: UUID,
        data: TradingAccountCreate,
    ) -> TradingAccount:
        """
        Create a trading account.

        The broker password is encrypted before being stored.
        """

        existing = await self.repository.get_by_identity(
            broker=data.broker,
            server=data.server,
            login=data.login,
        )

        if existing is not None:
            raise ValueError(
                "A trading account with this broker, server, "
                "and login already exists."
            )

        encrypted_credentials: str | None = None

        if data.password:
            encrypted_credentials = encrypt_secret(data.password)

        account = TradingAccount(
            user_id=user_id,
            broker=data.broker,
            login=data.login,
            server=data.server,
            account_name=data.account_name,
            is_demo=data.is_demo,
            bridge_url=data.bridge_url,
            credentials_encrypted=encrypted_credentials,
        )

        self.repository.add(account)

        await self.repository.commit()
        await self.repository.refresh(account)

        return account

    async def list_accounts(
        self,
        user_id: UUID,
    ) -> list[TradingAccount]:
        """
        Return all trading accounts belonging to a user.
        """

        return await self.repository.list_by_user(user_id=user_id)

    async def reconcile_bridge_state(
        self,
        user_id: UUID,
        bridge_status: dict | None,
    ) -> list[TradingAccount]:
        """Synchronize persisted account status with the live bridge session."""
        accounts = await self.repository.list_by_user(user_id=user_id)
        bridge_connected = bool(bridge_status and bridge_status.get("connected"))
        bridge_login = bridge_status.get("login") if bridge_status else None
        bridge_server = bridge_status.get("server") if bridge_status else None

        for account in accounts:
            if account.status == AccountStatus.ARCHIVED:
                continue

            if not bridge_status:
                next_status = AccountStatus.ERROR if account.status == AccountStatus.CONNECTED else account.status
            elif not bridge_connected:
                next_status = AccountStatus.DISCONNECTED
            else:
                matches = (
                    bridge_login is not None
                    and int(bridge_login) == account.login
                    and (bridge_server is None or bridge_server == account.server)
                )
                next_status = AccountStatus.CONNECTED if matches else AccountStatus.DISCONNECTED

            if account.status != next_status:
                account.status = next_status
                self.repository.update(account)

        await self.repository.commit()
        return accounts

    async def update_account(
        self,
        account_id: UUID,
        user_id: UUID,
        data: TradingAccountUpdate,
    ) -> TradingAccount:
        """
        Update a user-owned trading account.

        The password is never assigned directly to the database.
        If a new password is provided, it is encrypted first.
        """

        account = await self.get_owned_account(
            account_id=account_id,
            user_id=user_id,
        )

        update_data = data.model_dump(
            exclude_unset=True,
            exclude={"password"},
        )

        for field, value in update_data.items():
            setattr(
                account,
                field,
                value,
            )

        if data.password:
            account.credentials_encrypted = encrypt_secret(data.password)

        self.repository.update(account)

        await self.repository.commit()
        await self.repository.refresh(account)

        return account

    async def get_decrypted_credentials(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> str:
        """
        Retrieve and decrypt the broker password for an
        account owned by the authenticated user.

        The decrypted password should only be used internally
        for broker communication.
        """

        account = await self.get_owned_account(
            account_id=account_id,
            user_id=user_id,
        )

        if not account.credentials_encrypted:
            raise ValueError("Trading account credentials are not configured.")

        try:
            return decrypt_secret(account.credentials_encrypted)

        except Exception as exc:
            raise ValueError("Unable to decrypt trading account credentials.") from exc

    async def update_account_state(
        self,
        account_id: UUID,
        state: TradingAccountStateUpdate,
    ) -> TradingAccount:
        """
        Update broker-synchronized trading-account state.

        This method is intended for trusted internal
        synchronization from broker/bridge data.
        """

        account = await self.repository.get_by_id(account_id)

        if account is None:
            raise ValueError("Trading account not found.")

        state_data = state.model_dump(exclude_unset=True)

        for field, value in state_data.items():
            setattr(
                account,
                field,
                value,
            )

        self.repository.update(account)

        await self.repository.commit()
        await self.repository.refresh(account)

        return account

    async def set_active(
        self,
        account_id: UUID,
        user_id: UUID,
        active: bool,
    ) -> TradingAccount:
        """
        Enable or disable a user-owned trading account.
        """

        account = await self.get_owned_account(
            account_id=account_id,
            user_id=user_id,
        )

        account.active = active

        self.repository.update(account)

        await self.repository.commit()
        await self.repository.refresh(account)

        return account

    async def delete_account(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Delete a user-owned trading account.
        """

        account = await self.get_owned_account(
            account_id=account_id,
            user_id=user_id,
        )

        await self.repository.delete(account)

        await self.repository.commit()

    async def get_active_account(
        self,
        user_id: UUID,
    ) -> TradingAccount:
        """
        Retrieve the authenticated user's active trading account.

        An account is considered active for dashboard/engine use only
        when it is both enabled in AQE and currently connected to the
        broker bridge.
        """

        accounts = await self.repository.list_by_user(
            user_id=user_id,
        )

        active_accounts = [
            account
            for account in accounts
            if account.active
            and account.status == AccountStatus.CONNECTED
        ]

        if not active_accounts:
            raise ValueError(
                "No active connected trading account found."
            )

        if len(active_accounts) > 1:
            raise ValueError(
                "Multiple active connected trading accounts found."
            )

        return active_accounts[0]