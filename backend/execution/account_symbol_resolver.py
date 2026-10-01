
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.account_symbol import AccountSymbol
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)


class AccountSymbolResolutionError(Exception):
    """Raised when an AQE symbol cannot be resolved for an account."""


class AccountSymbolResolver:
    """
    Resolve account-specific AQE symbol mappings.

    AccountSymbol persistence contains two distinct identities:

        AQE canonical symbol
            e.g. ``XAUUSD``

        broker-facing symbol
            e.g. ``XAUUSD.s``

    Strategy runtime uses canonical AQE symbols.

    Broker execution uses broker-facing symbols.

    This resolver therefore exposes both operations:

        resolve()
            canonical AQE symbol -> broker symbol

        resolve_enabled_symbols()
            account -> enabled canonical AQE symbol universe

    Broker-specific symbol mapping belongs to AccountSymbol persistence,
    not to strategies, the execution engine, or individual broker
    adapters.

    Execution is permitted only when the required account-symbol
    mapping exists and is enabled.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self._repository = AccountSymbolRepository(
            db,
        )

    # ==================================================================
    # SINGLE SYMBOL RESOLUTION
    # ==================================================================

    async def resolve(
        self,
        *,
        account_id: UUID,
        symbol: str,
    ) -> str:
        """
        Resolve a canonical AQE symbol to its account-specific broker
        symbol.

        Example:

            account_id + "XAUUSD"
                -> "XAUUSD.s"

        The mapping must:

            1. belong to the requested trading account;
            2. reference the requested canonical AQE symbol;
            3. be enabled;
            4. contain a valid broker symbol.

        Raises:
            AccountSymbolResolutionError:
                If the mapping cannot safely be resolved.
        """

        self._validate_account_id(
            account_id,
        )

        canonical_symbol = self._normalize_symbol(
            symbol,
        )

        if not canonical_symbol:
            raise AccountSymbolResolutionError(
                "Symbol is required to resolve a broker symbol."
            )

        account_symbols = await self._repository.list_by_account(
            account_id,
        )

        matches = [
            account_symbol
            for account_symbol in account_symbols
            if self._matches_canonical_symbol(
                account_symbol,
                canonical_symbol,
            )
        ]

        if not matches:
            raise AccountSymbolResolutionError(
                f"No account-symbol mapping exists for "
                f"account_id={account_id} and "
                f"symbol={canonical_symbol!r}."
            )

        enabled_matches = [
            account_symbol
            for account_symbol in matches
            if self._is_enabled(
                account_symbol,
            )
        ]

        if not enabled_matches:
            raise AccountSymbolResolutionError(
                f"Account-symbol mapping for "
                f"account_id={account_id} and "
                f"symbol={canonical_symbol!r} is disabled."
            )

        if len(enabled_matches) > 1:
            raise AccountSymbolResolutionError(
                f"Multiple enabled account-symbol mappings exist for "
                f"account_id={account_id} and "
                f"symbol={canonical_symbol!r}."
            )

        account_symbol = enabled_matches[0]

        broker_symbol = self._normalize_symbol(
            account_symbol.broker_symbol,
        )

        if not broker_symbol:
            raise AccountSymbolResolutionError(
                f"Account symbol mapping for "
                f"{canonical_symbol!r} has no broker symbol."
            )

        return broker_symbol

    # ==================================================================
    # ACCOUNT SYMBOL UNIVERSE
    # ==================================================================

    async def resolve_enabled_symbols(
        self,
        *,
        account_id: UUID,
    ) -> tuple[str, ...]:
        """
        Resolve the current enabled canonical AQE symbols for an account.

        This is the authoritative strategy trading universe.

        Example:

            account symbols:

                XAUUSD  -> XAUUSD.s   enabled
                AUDCAD  -> AUDCAD.s   enabled
                BTCUSD  -> BTCUSD     disabled

            result:

                ("AUDCAD", "XAUUSD")

        The returned values are canonical AQE symbol names.

        Broker-facing names must remain out of StrategyConfig.

        Raises:
            AccountSymbolResolutionError:
                If the account ID is invalid or an enabled mapping is
                malformed.
        """

        self._validate_account_id(
            account_id,
        )

        account_symbols = await self._repository.list_by_account(
            account_id,
        )

        resolved: dict[str, AccountSymbol] = {}

        for account_symbol in account_symbols:
            if not self._is_enabled(
                account_symbol,
            ):
                continue

            canonical = self._canonical_symbol_name(
                account_symbol,
            )

            if not canonical:
                raise AccountSymbolResolutionError(
                    "An enabled account-symbol mapping has no "
                    "valid canonical AQE symbol."
                )

            broker_symbol = self._normalize_symbol(
                getattr(
                    account_symbol,
                    "broker_symbol",
                    None,
                )
            )

            if not broker_symbol:
                raise AccountSymbolResolutionError(
                    f"Enabled account-symbol mapping for "
                    f"canonical symbol {canonical!r} has no "
                    "valid broker symbol."
                )

            if canonical in resolved:
                existing = resolved[canonical]

                existing_broker_symbol = self._normalize_symbol(
                    getattr(
                        existing,
                        "broker_symbol",
                        None,
                    )
                )

                if existing_broker_symbol != broker_symbol:
                    raise AccountSymbolResolutionError(
                        f"Multiple enabled account-symbol mappings "
                        f"exist for canonical symbol {canonical!r} "
                        f"with different broker symbols: "
                        f"{existing_broker_symbol!r} and "
                        f"{broker_symbol!r}."
                    )

                raise AccountSymbolResolutionError(
                    f"Multiple enabled account-symbol mappings "
                    f"exist for canonical symbol {canonical!r}."
                )

            resolved[canonical] = account_symbol

        return tuple(
            sorted(
                resolved,
            )
        )

    # ==================================================================
    # CANONICAL SYMBOL HELPERS
    # ==================================================================

    @classmethod
    def _canonical_symbol_name(
        cls,
        account_symbol: AccountSymbol,
    ) -> str:
        """
        Return the canonical AQE symbol name from an AccountSymbol.
        """

        canonical = getattr(
            account_symbol,
            "symbol",
            None,
        )

        if canonical is None:
            return ""

        canonical_name = getattr(
            canonical,
            "name",
            None,
        )

        return cls._normalize_symbol(
            canonical_name,
        )

    @classmethod
    def _matches_canonical_symbol(
        cls,
        account_symbol: AccountSymbol,
        canonical_symbol: str,
    ) -> bool:
        """
        Match AccountSymbol against a canonical AQE symbol name.

        AccountSymbol.broker_symbol is the broker-facing name, while
        AccountSymbol.symbol.name is the canonical AQE name.
        """

        return (
            cls._canonical_symbol_name(
                account_symbol,
            )
            == canonical_symbol
        )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_account_id(
        account_id: UUID,
    ) -> None:
        """Validate an account UUID."""

        if not isinstance(
            account_id,
            UUID,
        ):
            raise AccountSymbolResolutionError(
                "A valid account UUID is required."
            )

    @staticmethod
    def _is_enabled(
        account_symbol: AccountSymbol,
    ) -> bool:
        """
        Determine whether an AccountSymbol is enabled.

        ``getattr`` is intentional so the resolver remains defensive
        against older model instances that may not expose the field.
        """

        return bool(
            getattr(
                account_symbol,
                "enabled",
                False,
            )
        )

    @staticmethod
    def _normalize_symbol(
        symbol: str | None,
    ) -> str:
        """
        Normalize a symbol name for comparison and runtime use.
        """

        if symbol is None:
            return ""

        return str(
            symbol,
        ).strip().upper()


__all__ = [
    "AccountSymbolResolutionError",
    "AccountSymbolResolver",
]
