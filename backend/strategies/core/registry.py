
"""Strategy registration and discovery for the AQE Strategy Engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .base import BaseStrategy
from .exceptions import (
    StrategyAlreadyRegisteredError,
    StrategyNotFoundError,
)


StrategyType = TypeVar("StrategyType", bound=type[BaseStrategy])


class StrategyRegistry:
    """
    Registry of available AQE strategy implementations.

    The registry stores strategy classes, not strategy instances.
    Runtime configuration is responsible for creating individual
    instances with their own symbols, timeframes, parameters, and mode.
    """

    def __init__(self) -> None:
        """Initialize an empty strategy registry."""

        self._strategies: dict[str, type[BaseStrategy]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a strategy registration name."""

        normalized = name.strip().lower()

        if not normalized:
            raise ValueError(
                "Strategy registration name cannot be empty."
            )

        return normalized

    def register(
        self,
        strategy_class: type[BaseStrategy],
        *,
        name: str | None = None,
        replace: bool = False,
    ) -> type[BaseStrategy]:
        """
        Register a strategy class.

        Args:
            strategy_class:
                Strategy implementation class to register.

            name:
                Optional registry name. When omitted, the strategy
                definition name is used.

            replace:
                Whether an existing registration may be replaced.

        Returns:
            The original strategy class.

        Raises:
            StrategyAlreadyRegisteredError:
                If the name is already registered and replace=False.
        """

        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError(
                "Only BaseStrategy subclasses can be registered."
            )

        registration_name = name or strategy_class.definition.name
        registration_name = self._normalize_name(registration_name)

        if (
            registration_name in self._strategies
            and not replace
        ):
            raise StrategyAlreadyRegisteredError(
                f"Strategy '{registration_name}' is already registered."
            )

        self._strategies[registration_name] = strategy_class

        return strategy_class

    def unregister(self, name: str) -> None:
        """
        Remove a strategy from the registry.

        Raises:
            StrategyNotFoundError:
                If the strategy is not registered.
        """

        registration_name = self._normalize_name(name)

        if registration_name not in self._strategies:
            raise StrategyNotFoundError(
                f"Strategy '{registration_name}' is not registered."
            )

        del self._strategies[registration_name]

    def get(self, name: str) -> type[BaseStrategy]:
        """
        Return a registered strategy class.

        Raises:
            StrategyNotFoundError:
                If the strategy is not registered.
        """

        registration_name = self._normalize_name(name)

        try:
            return self._strategies[registration_name]
        except KeyError as exc:
            raise StrategyNotFoundError(
                f"Strategy '{registration_name}' is not registered."
            ) from exc

    def contains(self, name: str) -> bool:
        """Return whether a strategy is registered."""

        registration_name = self._normalize_name(name)

        return registration_name in self._strategies

    def names(self) -> tuple[str, ...]:
        """Return all registered strategy names."""

        return tuple(sorted(self._strategies))

    def all(self) -> dict[str, type[BaseStrategy]]:
        """
        Return a shallow copy of the registered strategies.

        The registry's internal mapping cannot be modified through
        the returned dictionary.
        """

        return dict(self._strategies)

    def clear(self) -> None:
        """Remove all registered strategies."""

        self._strategies.clear()

    def __len__(self) -> int:
        """Return the number of registered strategies."""

        return len(self._strategies)

    def __contains__(self, name: str) -> bool:
        """Support the ``name in registry`` syntax."""

        return self.contains(name)


registry = StrategyRegistry()


def register_strategy(
    name: str | None = None,
    *,
    replace: bool = False,
) -> Callable[[StrategyType], StrategyType]:
    """
    Decorator for registering a strategy implementation.

    Example:

        @register_strategy("ema_cross")
        class EMACrossStrategy(BaseStrategy):
            ...

    The decorated class is returned unchanged, allowing normal class
    usage while registering it with the global strategy registry.
    """

    def decorator(
        strategy_class: StrategyType,
    ) -> StrategyType:
        registry.register(
            strategy_class,
            name=name,
            replace=replace,
        )

        return strategy_class

    return decorator
