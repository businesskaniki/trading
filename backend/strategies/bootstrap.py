"""AQE Strategy Engine bootstrap configuration."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from .discovery import (
    DEFAULT_STRATEGY_MODULES,
    StrategyDiscovery,
    StrategyDiscoveryResult,
)

logger = logging.getLogger(__name__)


class StrategyBootstrap:
    """
    Bootstrap the AQE Strategy Engine strategy registry.

    Bootstrap is responsible for loading the available strategy
    implementations into the StrategyRegistry.

    It does NOT:

        - create strategy instances
        - configure strategy instances
        - activate strategies
        - start strategies
        - pause strategies
        - stop strategy instances
        - subscribe to market data
        - consume Redis
        - perform risk checks
        - execute broker orders

    Runtime strategy instances are owned by StrategyManager.
    """

    def __init__(
        self,
        *,
        modules: Iterable[str] | None = None,
    ) -> None:
        """
        Initialize strategy bootstrap.

        Args:
            modules:
                Optional explicit strategy module collection.

                When omitted, the production AQE strategy modules
                defined by StrategyDiscovery are used.
        """

        self._modules = DEFAULT_STRATEGY_MODULES if modules is None else tuple(modules)

        self._discovery = StrategyDiscovery(
            modules=self._modules,
        )

        self._bootstrapped = False
        self._result: StrategyDiscoveryResult | None = None

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def discovery(self) -> StrategyDiscovery:
        """Return the underlying strategy discovery service."""

        return self._discovery

    @property
    def modules(self) -> tuple[str, ...]:
        """Return the strategy modules configured for bootstrap."""

        return self._modules

    @property
    def bootstrapped(self) -> bool:
        """Return whether bootstrap has completed successfully."""

        return self._bootstrapped

    @property
    def result(self) -> StrategyDiscoveryResult | None:
        """Return the most recent discovery result."""

        return self._result

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(self) -> StrategyDiscoveryResult:
        """
        Bootstrap the strategy registry.

        The operation is idempotent.

        Calling ``start()`` more than once returns the previous
        discovery result without re-importing already discovered
        modules.

        Bootstrap does not instantiate or activate any strategy.
        """

        if self._bootstrapped and self._result is not None:
            logger.debug("AQE Strategy Engine bootstrap already completed.")

            return self._result

        logger.info(
            "Starting AQE Strategy Engine bootstrap: modules=%s",
            self._modules,
        )

        try:
            result = self._discovery.discover()

        except Exception:
            self._bootstrapped = False
            self._result = None

            logger.exception("AQE Strategy Engine bootstrap failed.")

            raise

        self._result = result
        self._bootstrapped = True

        logger.info(
            "AQE Strategy Engine bootstrap completed: " "modules=%d strategies=%d",
            result.module_count,
            result.strategy_count,
        )

        logger.debug(
            "Registered AQE strategies: %s",
            result.registered_strategies,
        )

        return result

    async def stop(self) -> None:
        """
        Stop the bootstrap lifecycle.

        Bootstrap itself owns no running strategy instances.

        Therefore this operation does not unregister strategy classes
        and does not stop strategy instances.

        Strategy instances are owned and stopped by StrategyManager.
        """

        if not self._bootstrapped:
            return

        self._bootstrapped = False

        logger.info("AQE Strategy Engine bootstrap stopped.")

    # ==================================================================
    # DISCOVERY ACCESS
    # ==================================================================

    def registered_strategies(self) -> tuple[str, ...]:
        """
        Return the strategies discovered during the latest bootstrap.

        If bootstrap has not completed, an empty tuple is returned.
        """

        if self._result is None:
            return ()

        return self._result.registered_strategies


# ======================================================================
# DEFAULT APPLICATION BOOTSTRAP
# ======================================================================

strategy_bootstrap = StrategyBootstrap()
