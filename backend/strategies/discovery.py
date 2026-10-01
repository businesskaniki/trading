"""Strategy discovery and bootstrap for the AQE Strategy Engine."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from .core import StrategyRegistry, registry

logger = logging.getLogger(__name__)


# ======================================================================
# PRODUCTION STRATEGY MODULES
# ======================================================================

DEFAULT_STRATEGY_MODULES: tuple[str, ...] = (
    "strategies.implementations.bollinger_reversion",
    "strategies.implementations.donchian_breakout",
    "strategies.implementations.ema_trend",
    "strategies.implementations.macd_trend",
    "strategies.implementations.rsi_reversal",
)


@dataclass(frozen=True, slots=True)
class StrategyDiscoveryResult:
    """
    Result produced by the strategy discovery process.

    Discovery reports implementation modules that were successfully
    imported and strategy names that are currently registered.

    Discovery does not activate or instantiate strategies.
    """

    imported_modules: tuple[str, ...]
    registered_strategies: tuple[str, ...]

    @property
    def module_count(self) -> int:
        """Return the number of successfully imported modules."""

        return len(self.imported_modules)

    @property
    def strategy_count(self) -> int:
        """Return the number of registered strategies."""

        return len(self.registered_strategies)


class StrategyDiscovery:
    """
    Discover and import AQE strategy implementations.

    Discovery is responsible only for loading strategy classes and
    allowing their registration decorators to register them with the
    StrategyRegistry.

    Discovery does NOT:

        - create strategy instances
        - initialize strategies
        - activate strategies
        - start strategies
        - subscribe to market data
        - consume Redis
        - communicate with brokers
        - perform risk checks
        - execute orders
        - publish trading signals

    The runtime StrategyManager is responsible for creating and
    controlling strategy instances.
    """

    def __init__(
        self,
        *,
        strategy_registry: StrategyRegistry | None = None,
        modules: Iterable[str] | None = None,
    ) -> None:
        """
        Initialize strategy discovery.

        Args:
            strategy_registry:
                Registry that receives discovered strategy classes.

                When omitted, the global AQE registry is used.

            modules:
                Optional explicit collection of modules to import.

                When omitted, the five production AQE strategies defined
                in DEFAULT_STRATEGY_MODULES are imported.
        """

        self._registry = (
            strategy_registry if strategy_registry is not None else registry
        )

        if modules is None:
            self._modules = DEFAULT_STRATEGY_MODULES
        else:
            self._modules = self._normalize_modules(modules)

        self._imported_modules: set[str] = set()

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def registry(self) -> StrategyRegistry:
        """Return the registry used by this discovery instance."""

        return self._registry

    @property
    def modules(self) -> tuple[str, ...]:
        """Return the configured strategy modules."""

        return self._modules

    @property
    def imported_modules(self) -> tuple[str, ...]:
        """Return successfully imported modules in deterministic order."""

        return tuple(sorted(self._imported_modules))

    # ==================================================================
    # DISCOVERY
    # ==================================================================

    def discover(self) -> StrategyDiscoveryResult:
        """
        Import all configured strategy modules.

        Importing each implementation module executes its
        ``@register_strategy`` decorator, causing the strategy class to
        become available through the StrategyRegistry.

        No strategy instance is created.
        """

        imported: list[str] = []

        for module_name in self._modules:
            if module_name in self._imported_modules:
                continue

            self._import_module(module_name)

            self._imported_modules.add(module_name)
            imported.append(module_name)

        strategies = tuple(sorted(self._registry.names()))

        logger.info(
            "Strategy discovery completed: "
            "modules_imported=%d strategies_registered=%d",
            len(imported),
            len(strategies),
        )

        logger.debug(
            "Discovered strategy implementations: %s",
            strategies,
        )

        return StrategyDiscoveryResult(
            imported_modules=tuple(imported),
            registered_strategies=strategies,
        )

    def discover_module(
        self,
        module_name: str,
    ) -> StrategyDiscoveryResult:
        """
        Import one strategy module.

        This is useful for explicit dynamic discovery and testing.

        The imported module may register one or more strategy classes
        through the global or supplied StrategyRegistry.
        """

        normalized_module = self._normalize_module_name(
            module_name,
        )

        if normalized_module not in self._imported_modules:
            self._import_module(normalized_module)
            self._imported_modules.add(normalized_module)

        return StrategyDiscoveryResult(
            imported_modules=self.imported_modules,
            registered_strategies=tuple(sorted(self._registry.names())),
        )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _normalize_module_name(
        module_name: str,
    ) -> str:
        """Normalize and validate a Python module name."""

        if not isinstance(module_name, str):
            raise TypeError("Strategy module name must be a string.")

        normalized = module_name.strip()

        if not normalized:
            raise ValueError("Strategy module name cannot be empty.")

        return normalized

    @classmethod
    def _normalize_modules(
        cls,
        modules: Iterable[str],
    ) -> tuple[str, ...]:
        """
        Normalize an explicit module collection.

        Duplicate module names are removed while preserving the first
        occurrence.
        """

        normalized_modules: list[str] = []
        seen: set[str] = set()

        for module_name in modules:
            normalized = cls._normalize_module_name(
                module_name,
            )

            if normalized in seen:
                continue

            seen.add(normalized)
            normalized_modules.append(normalized)

        return tuple(normalized_modules)

    # ==================================================================
    # IMPORT
    # ==================================================================

    def _import_module(
        self,
        module_name: str,
    ) -> None:
        """
        Import a strategy implementation module.

        Import failures are allowed to propagate after being logged so
        that application startup or an explicit discovery operation
        cannot silently continue with a partially discovered strategy
        universe.
        """

        module_name = self._normalize_module_name(
            module_name,
        )

        logger.debug(
            "Loading strategy module: %s",
            module_name,
        )

        try:
            importlib.import_module(module_name)

        except Exception:
            logger.exception(
                "Failed to load strategy module: %s",
                module_name,
            )
            raise

        logger.debug(
            "Strategy module loaded successfully: %s",
            module_name,
        )


# ======================================================================
# BOOTSTRAP HELPER
# ======================================================================


def discover_strategies(
    *,
    strategy_registry: StrategyRegistry | None = None,
    modules: Iterable[str] | None = None,
) -> StrategyDiscoveryResult:
    """
    Discover the configured AQE strategy implementations.

    This is a convenience function for application bootstrap.

    It imports strategy modules and registers their classes, but does
    not create, initialize, activate, or start any strategy instance.
    """

    discovery = StrategyDiscovery(
        strategy_registry=strategy_registry,
        modules=modules,
    )

    return discovery.discover()
