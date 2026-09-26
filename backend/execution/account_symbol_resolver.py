from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.account_symbol import AccountSymbol
from app.repositories.account_symbol_repository import AccountSymbolRepository


class AccountSymbolResolutionError(Exception):
    """Raised when an AQE symbol cannot be resolved for an account."""


class AccountSymbolResolver:
    """
    Resolves an AQE canonical symbol to the broker-specific symbol
    configured for a trading account.

    Example:

        account_id + "XAUUSD"
            -> "XAUUSD.s"

    The resolver is deliberately broker-agnostic. Broker-specific symbol
    mapping belongs to AccountSymbol persistence, not the execution mapper
    or broker adapter.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._repository = AccountSymbolRepository(db)

    async def resolve(
        self,
        *,
        account_id: UUID,
        symbol: str,
    ) -> str:
        """
        Resolve a canonical AQE symbol to its account-specific broker symbol.
        """

        if not account_id:
            raise AccountSymbolResolutionError(
                "Account ID is required to resolve a broker symbol."
            )

        canonical_symbol = self._normalize_symbol(symbol)

        if not canonical_symbol:
            raise AccountSymbolResolutionError(
                "Symbol is required to resolve a broker symbol."
            )

        account_symbols = await self._repository.list_by_account(account_id)

        for account_symbol in account_symbols:
            if self._matches_canonical_symbol(
                account_symbol,
                canonical_symbol,
            ):
                broker_symbol = self._normalize_symbol(
                    account_symbol.broker_symbol
                )

                if not broker_symbol:
                    raise AccountSymbolResolutionError(
                        f"Account symbol mapping for "
                        f"{canonical_symbol!r} has no broker symbol."
                    )

                return broker_symbol

        raise AccountSymbolResolutionError(
            f"No account-symbol mapping exists for "
            f"account_id={account_id} and symbol={canonical_symbol!r}."
        )

    @staticmethod
    def _matches_canonical_symbol(
        account_symbol: AccountSymbol,
        canonical_symbol: str,
    ) -> bool:
        """
        Match against the canonical Symbol associated with AccountSymbol.

        AccountSymbol.broker_symbol is the broker-facing name, while
        AccountSymbol.symbol.name is the AQE canonical name.
        """

        canonical = getattr(account_symbol, "symbol", None)

        if canonical is None:
            return False

        canonical_name = getattr(canonical, "name", None)

        if not canonical_name:
            return False

        return str(canonical_name).strip().upper() == canonical_symbol

    @staticmethod
    def _normalize_symbol(symbol: str | None) -> str:
        if symbol is None:
            return ""

        return str(symbol).strip().upper()