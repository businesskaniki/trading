from __future__ import annotations

from uuid import UUID

from app.database.models.account_symbol import AccountSymbol
from app.database.models.symbol import Symbol
from app.database.models.trading_account import TradingAccount
from app.market_data.subscription_manager import (
    MarketDataSubscriptionManager,
)
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.schemas.account_symbol import AccountSymbolSync


class AccountSymbolService:
    """Business logic for account-specific trading symbols.

    AccountSymbol connects:

        TradingAccount
            +
        Canonical Symbol

    AccountSymbol.enabled determines whether AQE is permitted
    to trade that symbol on the specific trading account.

    Broker metadata is synchronized from MT5 and should not be
    edited by the frontend.

    Market-data subscriptions are reconciled after changes to
    AccountSymbol.enabled so that the MT5 Bridge reflects AQE's
    desired market-data state.
    """

    def __init__(
        self,
        account_symbol_repository: AccountSymbolRepository,
        trading_account_repository: TradingAccountRepository,
        subscription_manager: MarketDataSubscriptionManager | None = None,
    ) -> None:
        self.account_symbol_repository = account_symbol_repository
        self.trading_account_repository = trading_account_repository
        self.subscription_manager = subscription_manager

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
        """Synchronize broker/MT5 symbol metadata into AQE.

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

        return await self.account_symbol_repository.refresh(
            account_symbol,
        )

    # ==========================================================
    # ENABLE / DISABLE
    # ==========================================================

    async def set_enabled(
        self,
        account_symbol_id: UUID,
        user_id: UUID,
        enabled: bool,
    ) -> AccountSymbol:
        """Enable or disable trading for an account-specific symbol.

        Database state is committed before market-data
        subscription reconciliation.

        This is intentional:

            Database
                ↓
            Desired AQE state
                ↓
            Subscription reconciliation
                ↓
            MT5 Bridge

        A temporary MT5 Bridge failure therefore does not roll
        back the user's database selection.
        """

        account_symbol = await self.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=user_id,
        )

        account_symbol.enabled = enabled

        self.account_symbol_repository.update(account_symbol)

        await self.account_symbol_repository.commit()

        refreshed = await self.account_symbol_repository.refresh(
            account_symbol,
        )

        # ------------------------------------------------------
        # Reconcile market-data subscriptions
        # ------------------------------------------------------
        #
        # The database is already committed at this point.
        # The subscription manager reads the complete global
        # desired state from PostgreSQL and compares it with the
        # actual MT5 Bridge subscriptions.
        #
        # This is global rather than account-specific because
        # multiple trading accounts may use the same broker symbol.
        #
        if self.subscription_manager is not None:
            await self.subscription_manager.reconcile_symbol(
                refreshed.broker_symbol,
            )

        return refreshed

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
        """Enable or disable multiple account symbols.

        All database changes are committed first, followed by
        exactly one global market-data subscription reconciliation.

        This avoids performing a separate MT5 Bridge reconciliation
        for every symbol in a bulk operation.
        """

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

        # ------------------------------------------------------
        # Update all database records
        # ------------------------------------------------------

        for account_symbol in account_symbols:
            account_symbol.enabled = enabled
            self.account_symbol_repository.update(account_symbol)

        # ------------------------------------------------------
        # Commit database state first
        # ------------------------------------------------------

        await self.account_symbol_repository.commit()

        # ------------------------------------------------------
        # Refresh all updated records
        # ------------------------------------------------------

        refreshed_symbols: list[AccountSymbol] = []

        for account_symbol in account_symbols:
            refreshed = await self.account_symbol_repository.refresh(
                account_symbol,
            )
            refreshed_symbols.append(refreshed)

        # ------------------------------------------------------
        # Reconcile market-data subscriptions once
        # ------------------------------------------------------
        #
        # The manager calculates the complete global desired
        # subscription state. It therefore does not need to be
        # called once for every changed symbol.
        #
        if self.subscription_manager is not None:
            await self.subscription_manager.reconcile()

        return refreshed_symbols

    # ==========================================================
    # TRADING UNIVERSE
    # ==========================================================

    async def get_trading_universe(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> list[AccountSymbol]:
        """Return the account's currently enabled trading symbols."""

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
        """Delete an account-specific symbol.

        If the deleted symbol was enabled, the global subscription
        state is reconciled after the database deletion so the MT5
        Bridge subscription can be removed when no other account
        requires the same broker symbol.
        """

        account_symbol = await self.get_account_symbol(
            account_symbol_id=account_symbol_id,
            user_id=user_id,
        )

        was_enabled = account_symbol.enabled

        await self.account_symbol_repository.delete(
            account_symbol,
        )

        await self.account_symbol_repository.commit()

        # ------------------------------------------------------
        # If an enabled AccountSymbol was deleted, reconcile.
        # ------------------------------------------------------
        #
        # This is important because deletion can make a broker
        # symbol no longer required by any trading account.
        #
        if was_enabled and self.subscription_manager is not None:
            await self.subscription_manager.reconcile()
