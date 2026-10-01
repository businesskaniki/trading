"""Runtime strategy-to-account routing for the AQE Strategy Engine."""

from __future__ import annotations

from uuid import UUID

from ..core.signal import TradingSignal


class StrategyAccountRoutingError(RuntimeError):
    """Raised when a strategy cannot be resolved to a trading account."""


class StrategyAccountRouter:
    """
    Resolve runtime strategy instances to their assigned trading accounts.

    Account routing is a runtime concern.

    ``TradingSignal`` intentionally remains account-agnostic. A signal
    identifies the strategy instance that produced the trading intent,
    while this router resolves that strategy instance to the account on
    which the intent is allowed to operate.

    Runtime mapping:

        strategy_id -> account_id

    The StrategyManager owns registration and removal of these mappings.

    The downstream risk/execution pipeline can use ``resolve()`` when it
    needs to construct an account-scoped RiskContext.
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

        A concrete strategy runtime instance has exactly one account
        assignment. Registering the same strategy with the same account
        is idempotent. Registering it against another account is rejected.

        Args:
            strategy_id:
                Unique runtime identifier of the strategy instance.

            account_id:
                TradingAccount UUID assigned to the strategy.

        Raises:
            StrategyAccountRoutingError:
                If either identifier is invalid or the strategy is
                already assigned to another account.
        """

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        self._validate_account_id(
            account_id=account_id,
            strategy_id=normalized_strategy_id,
        )

        existing_account_id = self._routes.get(
            normalized_strategy_id,
        )

        if existing_account_id is not None:
            if existing_account_id == account_id:
                return

            raise StrategyAccountRoutingError(
                f"Strategy '{normalized_strategy_id}' is already "
                f"assigned to account '{existing_account_id}' and "
                f"cannot be reassigned to '{account_id}'."
            )

        self._routes[normalized_strategy_id] = account_id

    def unregister(
        self,
        strategy_id: str,
    ) -> UUID | None:
        """
        Remove a strategy-account assignment.

        Args:
            strategy_id:
                Runtime strategy instance identifier.

        Returns:
            The previously assigned account UUID, or ``None`` when
            no route existed.
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

        The signal itself remains account-agnostic. Its ``strategy_id``
        identifies the runtime strategy instance, which is resolved
        through this routing table.

        Args:
            signal:
                Trading signal produced by a strategy instance.

        Returns:
            The UUID of the trading account assigned to the strategy.

        Raises:
            StrategyAccountRoutingError:
                If the signal is invalid or the strategy has no
                registered account.
        """

        if not isinstance(
            signal,
            TradingSignal,
        ):
            raise StrategyAccountRoutingError(
                "Cannot resolve an account for an invalid " "TradingSignal."
            )

        strategy_id = self._normalize_strategy_id(
            signal.strategy_id,
        )

        account_id = self._routes.get(
            strategy_id,
        )

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
        Return the account assigned to a strategy.

        Args:
            strategy_id:
                Runtime strategy instance identifier.

        Returns:
            The assigned account UUID, or ``None`` when no route exists.
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
        """
        Return whether a strategy has an account assignment.

        Args:
            strategy_id:
                Runtime strategy instance identifier.

        Returns:
            ``True`` when a route exists, otherwise ``False``.
        """

        normalized_strategy_id = self._normalize_strategy_id(
            strategy_id,
        )

        return normalized_strategy_id in self._routes

    def clear(self) -> None:
        """Remove all strategy-account assignments."""

        self._routes.clear()

    @property
    def size(self) -> int:
        """Return the number of registered strategy-account routes."""

        return len(self._routes)

    def snapshot(self) -> dict[str, str]:
        """
        Return a serializable snapshot of all routing assignments.

        UUID values are converted to strings so the result can be
        returned directly by management or monitoring APIs.
        """

        return {
            strategy_id: str(account_id)
            for strategy_id, account_id in self._routes.items()
        }

    @staticmethod
    def _normalize_strategy_id(
        strategy_id: str,
    ) -> str:
        """
        Normalize and validate a strategy instance identifier.

        Strategy IDs are stripped but otherwise preserve their case.
        """

        if not isinstance(
            strategy_id,
            str,
        ):
            raise StrategyAccountRoutingError("Strategy ID must be a string.")

        normalized = strategy_id.strip()

        if not normalized:
            raise StrategyAccountRoutingError("Strategy ID cannot be empty.")

        return normalized

    @staticmethod
    def _validate_account_id(
        *,
        account_id: UUID,
        strategy_id: str,
    ) -> None:
        """Validate the account assigned to a strategy."""

        if not isinstance(
            account_id,
            UUID,
        ):
            raise StrategyAccountRoutingError(
                f"Invalid account ID for strategy " f"'{strategy_id}'."
            )
