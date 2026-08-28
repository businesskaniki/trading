"""
Strategy registry for the AQE strategy engine.

The registry is responsible for discovering and retrieving strategy
implementations.

It does NOT:
    - execute trades
    - connect to MT5
    - perform risk checks
    - manage positions
    - store trading signals

Its responsibility is simply to know which strategies are available.
"""

from __future__ import annotations

from typing import Iterable, Type

from .base import BaseStrategy
from .enums import StrategyCategory
from .exceptions import (
    StrategyAlreadyRegisteredError,
    StrategyNotFoundError,
)


class StrategyRegistry:
    """
    Central registry for AQE strategy implementations.

    Strategies are registered by their unique strategy_id.

    Example:

        registry = StrategyRegistry()

        registry.register(EMATrendStrategy)

        strategy = registry.create("ema_trend")
    """

    def __init__(
        self,
        strategies: Iterable[Type[BaseStrategy]] | None = None,
    ) -> None:
        self._strategies: dict[str, Type[BaseStrategy]] = {}

        if strategies:
            for strategy in strategies:
                self.register(strategy)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        strategy_class: Type[BaseStrategy],
        *,
        overwrite: bool = False,
    ) -> None:
        """
        Register a strategy class.

        Args:
            strategy_class:
                Concrete BaseStrategy subclass.

            overwrite:
                Replace an existing strategy with the same ID when True.

        Raises:
            TypeError:
                If the supplied class is not a BaseStrategy subclass.

            ValueError:
                If required strategy metadata is missing.

            StrategyAlreadyRegisteredError:
                If the strategy ID already exists and overwrite is False.
        """

        if not isinstance(strategy_class, type):
            raise TypeError("strategy_class must be a class")

        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError("strategy_class must inherit from BaseStrategy")

        strategy_id = getattr(
            strategy_class,
            "strategy_id",
            None,
        )

        if not strategy_id:
            raise ValueError("Strategy must define a non-empty strategy_id")

        if strategy_id in self._strategies and not overwrite:
            raise StrategyAlreadyRegisteredError(
                f"Strategy '{strategy_id}' is already registered",
                strategy_id=strategy_id,
            )

        self._strategies[strategy_id] = strategy_class

    # ------------------------------------------------------------------
    # Unregistration
    # ------------------------------------------------------------------

    def unregister(
        self,
        strategy_id: str,
    ) -> None:
        """
        Remove a strategy from the registry.

        Raises:
            StrategyNotFoundError:
                If the strategy does not exist.
        """

        if strategy_id not in self._strategies:
            raise StrategyNotFoundError(
                f"Strategy '{strategy_id}' is not registered",
                strategy_id=strategy_id,
            )

        del self._strategies[strategy_id]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        strategy_id: str,
    ) -> Type[BaseStrategy]:
        """
        Retrieve a strategy class by ID.

        Raises:
            StrategyNotFoundError:
                If the strategy does not exist.
        """

        strategy = self._strategies.get(strategy_id)

        if strategy is None:
            raise StrategyNotFoundError(
                f"Strategy '{strategy_id}' is not registered",
                strategy_id=strategy_id,
            )

        return strategy

    def create(
        self,
        strategy_id: str,
    ) -> BaseStrategy:
        """
        Create a new strategy instance by ID.
        """

        strategy_class = self.get(strategy_id)

        return strategy_class()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def contains(
        self,
        strategy_id: str,
    ) -> bool:
        """
        Return whether a strategy is registered.
        """

        return strategy_id in self._strategies

    def all(self) -> tuple[Type[BaseStrategy], ...]:
        """
        Return all registered strategy classes.
        """

        return tuple(self._strategies.values())

    def ids(self) -> tuple[str, ...]:
        """
        Return all registered strategy IDs.
        """

        return tuple(self._strategies.keys())

    def count(self) -> int:
        """
        Return the number of registered strategies.
        """

        return len(self._strategies)

    def by_category(
        self,
        category: StrategyCategory,
    ) -> tuple[Type[BaseStrategy], ...]:
        """
        Return strategies belonging to a category.
        """

        return tuple(
            strategy
            for strategy in self._strategies.values()
            if strategy.category == category
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def metadata(self) -> tuple[dict[str, object], ...]:
        """
        Return metadata for every registered strategy.
        """

        return tuple(strategy.metadata() for strategy in self._strategies.values())

    def clear(self) -> None:
        """
        Remove all registered strategies.

        Primarily useful for tests and controlled initialization.
        """

        self._strategies.clear()

    # ------------------------------------------------------------------
    # Python protocol
    # ------------------------------------------------------------------

    def __contains__(
        self,
        strategy_id: str,
    ) -> bool:
        return self.contains(strategy_id)

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return f"StrategyRegistry(" f"strategies={list(self._strategies.keys())}" f")"
