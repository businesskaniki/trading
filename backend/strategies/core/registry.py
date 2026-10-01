"""Strategy registration and discovery for the AQE Strategy Engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .base import BaseStrategy, StrategyDefinition
from .exceptions import (
    StrategyAlreadyRegisteredError,
    StrategyNotFoundError,
)


StrategyType = TypeVar(
    "StrategyType",
    bound=type[BaseStrategy],
)


class StrategyRegistry:
    """
    Registry of available AQE strategy implementations.

    The registry stores strategy classes, not strategy instances.

    Its responsibility is to answer:

        "What strategy implementations exist?"

    It does NOT answer:

        "Which strategies are currently active?"

    Runtime activation, configuration, lifecycle, selected symbols,
    parameters, and execution mode belong to the strategy runtime layer.
    """

    def __init__(self) -> None:
        """Initialize an empty strategy registry."""

        self._strategies: dict[str, type[BaseStrategy]] = {}

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Normalize a strategy registration name.

        Strategy names are case-insensitive at the registry boundary.
        """

        if not isinstance(name, str):
            raise TypeError(
                "Strategy registration name must be a string."
            )

        normalized = name.strip().lower()

        if not normalized:
            raise ValueError(
                "Strategy registration name cannot be empty."
            )

        return normalized

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_strategy_class(
        strategy_class: type[BaseStrategy],
    ) -> StrategyDefinition:
        """
        Validate a strategy implementation class.

        Returns:
            The strategy's static definition.

        Raises:
            TypeError:
                If the supplied object is not a BaseStrategy subclass.

            TypeError:
                If the class does not expose a valid
                StrategyDefinition.
        """

        if not isinstance(strategy_class, type):
            raise TypeError(
                "Only strategy classes can be registered."
            )

        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError(
                "Only BaseStrategy subclasses can be registered."
            )

        definition = getattr(
            strategy_class,
            "definition",
            None,
        )

        if not isinstance(definition, StrategyDefinition):
            raise TypeError(
                f"Strategy class '{strategy_class.__name__}' must "
                "define a class-level StrategyDefinition."
            )

        return definition

    # ==================================================================
    # REGISTRATION
    # ==================================================================

    def register(
        self,
        strategy_class: type[BaseStrategy],
        *,
        name: str | None = None,
        replace: bool = False,
    ) -> type[BaseStrategy]:
        """
        Register a strategy implementation class.

        Args:
            strategy_class:
                Concrete BaseStrategy implementation.

            name:
                Optional registry name.

                When omitted, ``strategy_class.definition.name`` is
                used as the canonical registration name.

                When supplied, it is treated as the registry name for
                this implementation. The class definition itself remains
                the source of truth for strategy metadata.

            replace:
                Allow an existing registration to be replaced.

        Returns:
            The original strategy class.

        Raises:
            TypeError:
                If the class is not a valid strategy implementation.

            StrategyAlreadyRegisteredError:
                If the registration name already exists and replacement
                is not explicitly allowed.
        """

        definition = self._validate_strategy_class(
            strategy_class,
        )

        registration_name = (
            name
            if name is not None
            else definition.name
        )

        registration_name = self._normalize_name(
            registration_name,
        )

        if (
            registration_name in self._strategies
            and not replace
        ):
            existing_class = self._strategies[
                registration_name
            ]

            raise StrategyAlreadyRegisteredError(
                f"Strategy '{registration_name}' is already "
                f"registered by "
                f"'{existing_class.__name__}'."
            )

        self._strategies[registration_name] = strategy_class

        logger_name = (
            strategy_class.__module__
            + "."
            + strategy_class.__qualname__
        )

        # Keep registration side-effect free apart from storing the
        # class. Logging is intentionally lightweight because discovery
        # may import several strategy modules during application startup.
        import logging

        logging.getLogger(__name__).debug(
            "Strategy registered: name=%s implementation=%s "
            "definition=%s version=%s",
            registration_name,
            logger_name,
            definition.name,
            definition.version,
        )

        return strategy_class

    def unregister(
        self,
        name: str,
    ) -> None:
        """
        Remove a strategy implementation from the registry.

        This only removes the implementation from discovery.

        It does not stop or deactivate an already-created runtime
        strategy instance.
        """

        registration_name = self._normalize_name(name)

        if registration_name not in self._strategies:
            raise StrategyNotFoundError(
                f"Strategy '{registration_name}' is not registered."
            )

        del self._strategies[registration_name]

    # ==================================================================
    # LOOKUP
    # ==================================================================

    def get(
        self,
        name: str,
    ) -> type[BaseStrategy]:
        """
        Return a registered strategy implementation class.

        The returned object is a class, not an instantiated strategy.
        """

        registration_name = self._normalize_name(name)

        try:
            return self._strategies[registration_name]

        except KeyError as exc:
            raise StrategyNotFoundError(
                f"Strategy '{registration_name}' is not registered."
            ) from exc

    def get_definition(
        self,
        name: str,
    ) -> StrategyDefinition:
        """
        Return the static definition of a registered strategy.

        No strategy instance is created.
        """

        strategy_class = self.get(name)

        return strategy_class.definition

    def contains(
        self,
        name: str,
    ) -> bool:
        """Return whether a strategy is registered."""

        registration_name = self._normalize_name(name)

        return registration_name in self._strategies

    # ==================================================================
    # DISCOVERY INFORMATION
    # ==================================================================

    def names(self) -> tuple[str, ...]:
        """
        Return all registered strategy names.

        Names are returned in deterministic alphabetical order.
        """

        return tuple(
            sorted(self._strategies),
        )

    def definitions(self) -> tuple[StrategyDefinition, ...]:
        """
        Return definitions for all registered strategies.

        Definitions are returned in the same deterministic order as
        ``names()``.
        """

        return tuple(
            self._strategies[name].definition
            for name in self.names()
        )

    def describe(
        self,
        name: str,
    ) -> dict[str, object]:
        """
        Return a serializable description of a registered strategy.

        This is useful for management APIs and frontend discovery.
        """

        strategy_class = self.get(name)
        definition = strategy_class.definition

        return {
            "name": definition.name,
            "version": definition.version,
            "description": definition.description,
            "author": definition.author,
            "tags": list(definition.tags),
            "implementation": (
                f"{strategy_class.__module__}."
                f"{strategy_class.__qualname__}"
            ),
        }

    def all_descriptions(self) -> tuple[dict[str, object], ...]:
        """
        Return descriptions of all registered strategies.
        """

        return tuple(
            self.describe(name)
            for name in self.names()
        )

    def all(
        self,
    ) -> dict[str, type[BaseStrategy]]:
        """
        Return a shallow copy of the registered strategy mapping.

        Modifying the returned dictionary does not modify the registry.
        """

        return dict(self._strategies)

    # ==================================================================
    # REGISTRY MANAGEMENT
    # ==================================================================

    def clear(self) -> None:
        """
        Remove all registered strategy implementations.

        This is primarily useful for tests and controlled discovery
        reloads.
        """

        self._strategies.clear()

    def __len__(self) -> int:
        """Return the number of registered strategies."""

        return len(self._strategies)

    def __contains__(
        self,
        name: str,
    ) -> bool:
        """Support ``name in registry`` syntax."""

        return self.contains(name)

    def __iter__(self):
        """Iterate over registered strategy names."""

        return iter(self.names())


# ======================================================================
# GLOBAL REGISTRY
# ======================================================================

registry = StrategyRegistry()


# ======================================================================
# REGISTRATION DECORATOR
# ======================================================================

def register_strategy(
    name: str | None = None,
    *,
    replace: bool = False,
) -> Callable[[StrategyType], StrategyType]:
    """
    Decorator for registering a strategy implementation.

    Example:

        @register_strategy()
        class EMATrendStrategy(BaseStrategy):
            definition = StrategyDefinition(
                name="ema_trend",
                ...
            )

    Or explicitly:

        @register_strategy("ema_trend")
        class EMATrendStrategy(BaseStrategy):
            ...

    The decorated class is returned unchanged, allowing normal class
    usage while registering it with the global registry.

    Registration does not instantiate, initialize, activate, or start
    the strategy.
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