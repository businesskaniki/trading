"""Strategy discovery and bootstrap for the AQE Strategy Engine."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from .core import StrategyRegistry, registry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StrategyDiscoveryResult:
    """
    Result produced by the strategy discovery process.

    Attributes:
        imported_modules:
            Modules successfully imported.

        registered_strategies:
            Strategy names available in the registry after discovery.
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
    Discover and import AQE strategy modules.

    Discovery is responsible only for loading strategy definitions.

    It does not:
        - create strategy instances
        - start strategies
        - subscribe to market data
        - consume Redis
        - communicate with brokers
        - execute orders
        - publish trading signals
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
                Registry that receives discovered strategies.

            modules:
                Optional explicit list of strategy modules.

                When supplied, only these modules are imported.
        """

        self._registry = strategy_registry or registry
        self._modules = tuple(modules or ())
        self._imported_modules: set[str] = set()

    @property
    def registry(self) -> StrategyRegistry:
        """Return the registry used by discovery."""

        return self._registry

    @property
    def imported_modules(self) -> tuple[str, ...]:
        """Return successfully imported modules."""

        return tuple(sorted(self._imported_modules))

    def discover(self) -> StrategyDiscoveryResult:
        """
        Import configured strategy modules.

        Importing a strategy module executes its registration
        decorator, making the strategy class available through
        the StrategyRegistry.
        """

        imported: list[str] = []

        for module_name in self._modules:
            if module_name in self._imported_modules:
                continue

            self._import_module(module_name)

            imported.append(module_name)
            self._imported_modules.add(module_name)

        strategies = tuple(
            sorted(self._registry.names())
        )

        logger.info(
            "Strategy discovery completed: "
            "modules=%d strategies=%d",
            len(imported),
            len(strategies),
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

        This is useful for dynamically loading a strategy without
        rebuilding the entire discovery configuration.
        """

        if module_name not in self._imported_modules:
            self._import_module(module_name)
            self._imported_modules.add(module_name)

        return StrategyDiscoveryResult(
            imported_modules=self.imported_modules,
            registered_strategies=tuple(
                sorted(self._registry.names())
            ),
        )

    def _import_module(
        self,
        module_name: str,
    ) -> None:
        """Import a strategy module and provide a useful failure."""

        if not module_name.strip():
            raise ValueError(
                "Strategy module name cannot be empty."
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