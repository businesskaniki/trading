"""Runtime strategy-to-account routing for the AQE Strategy Engine."""

from __future__ import annotations

from uuid import UUID

from strategies.core.signal import TradingSignal


class StrategyAccountRoutingError(RuntimeError):
    """Raised when a strategy cannot be resolved to a trading account."""


class StrategyAccountRouter:
    """
    Resolve strategy instances to their assigned trading accounts.

    Account routing is a runtime concern. TradingSignal intentionally
    remains account-agnostic and identifies only the strategy instance
    that produced the trading intent.

    The router therefore maintains:

        strategy_id -> account_id

    The StrategyManager owns registration and removal of these mappings.
    The risk/execution pipeline uses ``resolve`` when it needs to build
    an account-scoped RiskContext.
    """

    def __init__(self) -> None:
        """Initialize an empty strategy-account routing table."""

        self._routes: dict[str, UUID] = {}

    def register(
        self,
        *,
        strategy_id: str,
        account_id: UUID,
    ) -> None:
        """
        Register a strategy instance against a trading account.

        A strategy ID represents one concrete runtime instance and must
        therefore have exactly one account assignment.

        Raises:
            StrategyAccountRoutingError:
                If the strategy ID is invalid, the account ID is invalid,
                or the strategy is already registered to another account.
        """

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        if not isinstance(account_id, UUID):
            raise StrategyAccountRoutingError(
                f"Invalid account ID for strategy " f"'{normalized_strategy_id}'."
            )

        existing_account_id = self._routes.get(
            normalized_strategy_id,
        )

        if existing_account_id is not None:
            if existing_account_id == account_id:
                return

            raise StrategyAccountRoutingError(
                f"Strategy '{normalized_strategy_id}' is already "
                f"assigned to account '{existing_account_id}'."
            )

        self._routes[normalized_strategy_id] = account_id

    def unregister(
        self,
        strategy_id: str,
    ) -> UUID | None:
        """
        Remove a strategy-account assignment.

        Returns:
            The previously assigned account ID, or None when the
            strategy was not registered.
        """

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        return self._routes.pop(
            normalized_strategy_id,
            None,
        )

    def resolve(
        self,
        signal: TradingSignal,
    ) -> UUID:
        """
        Resolve the trading account for a strategy signal.

        The signal remains account-agnostic. Its strategy_id identifies
        the runtime strategy instance, which is then resolved through
        this routing table.

        Raises:
            StrategyAccountRoutingError:
                If the signal is invalid or its strategy has no
                registered account.
        """

        if not isinstance(signal, TradingSignal):
            raise StrategyAccountRoutingError(
                "Cannot resolve an account for an invalid trading signal."
            )

        strategy_id = self._normalize_strategy_id(
            signal.strategy_id,
        )

        account_id = self._routes.get(strategy_id)

        if account_id is None:
            raise StrategyAccountRoutingError(
                f"No trading account is assigned to strategy " f"'{strategy_id}'."
            )

        return account_id

    def get(
        self,
        strategy_id: str,
    ) -> UUID | None:
        """
        Return the account assigned to a strategy, if registered.
        """

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        return self._routes.get(
            normalized_strategy_id,
        )

    def contains(
        self,
        strategy_id: str,
    ) -> bool:
        """Return whether a strategy has an account assignment."""

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        return normalized_strategy_id in self._routes

    def clear(self) -> None:
        """Remove all strategy-account assignments."""

        self._routes.clear()

    @property
    def size(self) -> int:
        """Return the number of registered strategy routes."""

        return len(self._routes)

    def snapshot(self) -> dict[str, str]:
        """
        Return a diagnostic snapshot of all routing assignments.

        UUIDs are converted to strings so the result is directly
        serializable by monitoring and management APIs.
        """

        return {
            strategy_id: str(account_id)
            for strategy_id, account_id in self._routes.items()
        }

    @staticmethod
    def _normalize_strategy_id(
        strategy_id: str,
    ) -> str:
        """Normalize and validate a strategy instance identifier."""

        if not isinstance(strategy_id, str):
            raise StrategyAccountRoutingError("Strategy ID must be a string.")

        normalized = strategy_id.strip()

        if not normalized:
            raise StrategyAccountRoutingError("Strategy ID cannot be empty.")

        return normalized
