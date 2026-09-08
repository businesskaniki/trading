from __future__ import annotations

from uuid import UUID

from app.database.models.account_symbol import AccountSymbol
from app.database.models.symbol import Symbol
from app.database.models.trading_account import TradingAccount
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.schemas.account_symbol import AccountSymbolSync


class AccountSymbolService:
    """
    Business logic for account-specific trading symbols.

    AccountSymbol connects:

        TradingAccount
            +
        Canonical Symbol

    AccountSymbol.enabled determines whether AQE is permitted
    to trade that symbol on the specific trading account.

    Broker metadata is synchronized from MT5 and should not be
    edited by the frontend.
    """

    def __init__(
        self,
        account_symbol_repository: AccountSymbolRepository,
        trading_account_repository: TradingAccountRepository,
    ) -> None:
        self.account_symbol_repository = account_symbol_repository
        self.trading_account_repository = trading_account_repository

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def get_account(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> TradingAccount:
        account = await self.trading_account_repository.get_by_id_and_user(
            account_id=account_id,
            user_id=user_id,
        )

        if account is None:
            raise ValueError("Trading account not found.")

        return account

    # ==========================================================
    # ACCOUNT SYMBOL
    # ==========================================================

    async def get_account_symbol(
        self,
        account_symbol_id: UUID,
        user_id: UUID,
    ) -> AccountSymbol:
        account_symbol = await self.account_symbol_repository.get_by_id_and_user(
            account_symbol_id=account_symbol_id,
            user_id=user_id,
        )

        if account_symbol is None:
            raise ValueError("Account symbol not found.")

        return account_symbol

    # ==========================================================
    # LIST
    # ==========================================================

    async def list_account_symbols(
        self,
        account_id: UUID,
        user_id: UUID,
        enabled_only: bool = False,
    ) -> list[AccountSymbol]:

        await self.get_account(
            account_id=account_id,
            user_id=user_id,
        )

        if enabled_only:
            return await self.account_symbol_repository.list_enabled_by_account(
                account_id=account_id,
            )

        return await self.account_symbol_repository.list_by_account(
            account_id=account_id,
        )

    # ==========================================================
    # BROKER SYMBOL
    # ==========================================================

    async def get_by_broker_symbol(
        self,
        account_id: UUID,
        broker_symbol: str,
    ) -> AccountSymbol | None:

        return await self.account_symbol_repository.get_by_broker_symbol(
            account_id=account_id,
            broker_symbol=broker_symbol,
        )

    # ==========================================================
    # SYNCHRONIZATION
    # ==========================================================

    async def sync_symbol(
        self,
        account_id: UUID,
        symbol: Symbol,
        data: AccountSymbolSync,
    ) -> AccountSymbol:
        """
        Synchronize broker/MT5 symbol metadata into AQE.

        Existing enabled state is deliberately preserved.

        This method is intended for backend synchronization
        workflows, not direct frontend use.
        """

        account_symbol = await self.account_symbol_repository.get_by_broker_symbol(
            account_id=account_id,
            broker_symbol=data.broker_symbol,
        )

        if account_symbol is None:
            account_symbol = AccountSymbol(
                account_id=account_id,
                symbol_id=symbol.id,
                broker_symbol=data.broker_symbol,
                path=data.path,
                currency_base=data.currency_base,
                currency_profit=data.currency_profit,
                currency_margin=data.currency_margin,
                digits=data.digits,
                point=data.point,
                tick_size=(
                    data.tick_size if data.tick_size is not None else data.point
                ),
                contract_size=data.contract_size,
                min_volume=data.min_volume,
                max_volume=data.max_volume,
                volume_step=data.volume_step,
                visible=data.visible,
                enabled=False,
            )

            self.account_symbol_repository.add(account_symbol)

        else:
            account_symbol.symbol_id = symbol.id
            account_symbol.path = data.path
            account_symbol.currency_base = data.currency_base
            account_symbol.currency_profit = data.currency_profit
            account_symbol.currency_margin = data.currency_margin
            account_symbol.digits = data.digits
            account_symbol.point = data.point

            if data.tick_size is not None:
                account_symbol.tick_size = data.tick_size
            else:
                account_symbol.tick_size = data.point

            account_symbol.contract_size = data.contract_size
            account_symbol.min_volume = data.min_volume
            account_symbol.max_volume = data.max_volume
            account_symbol.volume_step = data.volume_step
            account_symbol.visible = data.visible

            self.account_symbol_repository.update(account_symbol)

        await self.account_symbol_repository.flush()
        await self.account_symbol_repository.commit()
        await self.account_symbol_repository.refresh(account_symbol)

        return account_symbol

    # ==========================================================
    # ENABLE / DISABLE
    # ==========================================================

    async def set_enabled(
        self,
        account_symbol_id: UUID,
        user_id: UUID,
        enabled: bool,
    ) -> AccountSymbol:

        account_symbol = await self.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=user_id,
        )

        account_symbol.enabled = enabled

        self.account_symbol_repository.update(account_symbol)

        await self.account_symbol_repository.commit()
        await self.account_symbol_repository.refresh(account_symbol)

        return account_symbol

    # ==========================================================
    # BULK ENABLE / DISABLE
    # ==========================================================

    async def set_multiple_enabled(
        self,
        account_id: UUID,
        user_id: UUID,
        account_symbol_ids: list[UUID],
        enabled: bool,
    ) -> list[AccountSymbol]:

        await self.get_account(
            account_id=account_id,
            user_id=user_id,
        )

        if not account_symbol_ids:
            return []

        account_symbols = await self.account_symbol_repository.list_by_account_and_ids(
            account_id=account_id,
            account_symbol_ids=account_symbol_ids,
        )

        found_ids = {account_symbol.id for account_symbol in account_symbols}

        missing_ids = set(account_symbol_ids) - found_ids

        if missing_ids:
            raise ValueError(
                "One or more account symbols do not belong " "to this trading account."
            )

        for account_symbol in account_symbols:
            account_symbol.enabled = enabled
            self.account_symbol_repository.update(account_symbol)

        await self.account_symbol_repository.commit()

        for account_symbol in account_symbols:
            await self.account_symbol_repository.refresh(account_symbol)

        return account_symbols

    # ==========================================================
    # TRADING UNIVERSE
    # ==========================================================

    async def get_trading_universe(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> list[AccountSymbol]:

        return await self.list_account_symbols(
            account_id=account_id,
            user_id=user_id,
            enabled_only=True,
        )

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_account_symbol(
        self,
        account_symbol_id: UUID,
        user_id: UUID,
    ) -> None:

        account_symbol = await self.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=user_id,
        )

        await self.account_symbol_repository.delete(account_symbol)

        await self.account_symbol_repository.commit()
