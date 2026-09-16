"""AQE Strategy Engine bootstrap configuration."""

from __future__ import annotations

import logging

from .discovery import StrategyDiscovery, StrategyDiscoveryResult

logger = logging.getLogger(__name__)


DEFAULT_STRATEGY_MODULES: tuple[str, ...] = (
    "strategies.implementations.ema_trend",
    "strategies.implementations.rsi_reversal",
    "strategies.implementations.macd_trend",
)

class StrategyBootstrap:
    """
    Bootstrap the AQE Strategy Engine strategy registry.

    The bootstrap layer defines which strategy modules belong to
    the running AQE application.

    It does not create or start strategy instances.
    """

    def __init__(
        self,
        *,
        modules: tuple[str, ...] | None = None,
    ) -> None:
        """
        Initialize strategy bootstrap.

        Args:
            modules:
                Optional explicit strategy module list.

                When omitted, AQE's default strategy modules are used.
        """

        self._modules = DEFAULT_STRATEGY_MODULES if modules is None else tuple(modules)

        self._discovery = StrategyDiscovery(
            modules=self._modules,
        )

        self._bootstrapped = False
        self._result: StrategyDiscoveryResult | None = None

    @property
    def discovery(self) -> StrategyDiscovery:
        """Return the underlying discovery service."""

        return self._discovery

    @property
    def bootstrapped(self) -> bool:
        """Return whether bootstrap has completed."""

        return self._bootstrapped

    @property
    def result(self) -> StrategyDiscoveryResult | None:
        """Return the most recent discovery result."""

        return self._result

    async def start(self) -> StrategyDiscoveryResult:
        """
        Bootstrap the strategy registry.

        The operation is idempotent. Calling start more than once
        does not import the same modules repeatedly.
        """

        if self._bootstrapped and self._result is not None:
            return self._result

        logger.info("Starting AQE Strategy Engine bootstrap.")

        result = self._discovery.discover()

        self._result = result
        self._bootstrapped = True

        logger.info(
            "AQE Strategy Engine bootstrap completed: " "modules=%d strategies=%d",
            result.module_count,
            result.strategy_count,
        )

        return result

    async def stop(self) -> None:
        """
        Stop the bootstrap lifecycle.

        Strategy classes remain registered because discovery is
        process-level configuration. Runtime strategy instances
        are owned by StrategyManager and must be stopped there.
        """

        self._bootstrapped = False

        logger.info("AQE Strategy Engine bootstrap stopped.")


strategy_bootstrap = StrategyBootstrap()
