"""Dependency management for the Athena Quant Engine.

This module provides the application's shared runtime dependencies.

The dependency layer is intentionally responsible for composition and
lifecycle ownership, not business logic. Concrete implementations can be
injected during application startup and replaced with test doubles during
testing.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any, Iterator, Protocol

from engine.core.settings import AQESettings, get_settings


class Closeable(Protocol):
    """Protocol for resources that can be closed."""

    def close(self) -> Any:
        """Release the resource."""
        ...


class Startable(Protocol):
    """Protocol for resources that can be started."""

    def start(self) -> Any:
        """Start the resource."""
        ...


class Stoppable(Protocol):
    """Protocol for resources that can be stopped."""

    def stop(self) -> Any:
        """Stop the resource."""
        ...


@dataclass(slots=True)
class EngineDependencies:
    """Container for shared AQE runtime dependencies.

    Dependencies are deliberately typed as ``Any`` at this layer because
    the engine should be able to compose the existing AQE implementations
    without creating hard imports between every subsystem.

    Concrete implementations are supplied during application startup.
    """

    settings: AQESettings

    database: Any = None
    redis: Any = None

    event_bus: Any = None
    broker_manager: Any = None

    market_feed: Any = None
    strategy_manager: Any = None

    risk_manager: Any = None
    execution_engine: Any = None

    portfolio_manager: Any = None
    analytics: Any = None

    backtesting_engine: Any = None
    monitoring: Any = None

    ml_engine: Any = None

    def validate(self) -> None:
        """Validate dependencies required by the current runtime mode."""

        self.settings.validate_runtime_safety()

        if self.settings.market.enabled and self.market_feed is None:
            raise RuntimeError(
                "Market feed dependency is required while market data " "is enabled."
            )

        if self.settings.risk.enabled and self.risk_manager is None:
            raise RuntimeError(
                "Risk manager dependency is required while risk management "
                "is enabled."
            )

        if self.broker_manager is None:
            raise RuntimeError("Broker manager dependency is required.")

        if self.execution_engine is None:
            raise RuntimeError("Execution engine dependency is required.")

        if self.portfolio_manager is None:
            raise RuntimeError("Portfolio manager dependency is required.")

        if self.event_bus is None:
            raise RuntimeError("Event bus dependency is required.")

    def start(self) -> None:
        """Start dependencies that expose a start lifecycle method."""

        resources = (
            self.database,
            self.redis,
            self.event_bus,
            self.market_feed,
            self.broker_manager,
            self.strategy_manager,
            self.risk_manager,
            self.execution_engine,
            self.portfolio_manager,
            self.analytics,
            self.monitoring,
            self.ml_engine,
        )

        for resource in resources:
            _call_lifecycle_method(resource, "start")

    def stop(self) -> None:
        """Stop dependencies in reverse ownership order."""

        resources = (
            self.ml_engine,
            self.monitoring,
            self.analytics,
            self.portfolio_manager,
            self.execution_engine,
            self.risk_manager,
            self.strategy_manager,
            self.broker_manager,
            self.market_feed,
            self.event_bus,
            self.redis,
            self.database,
        )

        errors: list[Exception] = []

        for resource in resources:
            try:
                _call_lifecycle_method(resource, "stop")
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise RuntimeError(
                f"{len(errors)} AQE dependency shutdown operation(s) failed."
            ) from errors[0]

    def close(self) -> None:
        """Close dependencies that expose a close method."""

        resources = (
            self.ml_engine,
            self.monitoring,
            self.analytics,
            self.portfolio_manager,
            self.execution_engine,
            self.risk_manager,
            self.strategy_manager,
            self.broker_manager,
            self.market_feed,
            self.event_bus,
            self.redis,
            self.database,
        )

        errors: list[Exception] = []

        for resource in resources:
            try:
                _call_lifecycle_method(resource, "close")
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise RuntimeError(
                f"{len(errors)} AQE dependency close operation(s) failed."
            ) from errors[0]


def _call_lifecycle_method(
    resource: Any,
    method_name: str,
) -> None:
    """Call a lifecycle method when a dependency provides one."""

    if resource is None:
        return

    method = getattr(resource, method_name, None)

    if method is None:
        return

    result = method()

    # Lifecycle methods may be synchronous or asynchronous.
    # Async lifecycle ownership is handled by the application lifecycle
    # layer rather than silently running an event loop here.
    if hasattr(result, "__await__"):
        raise RuntimeError(
            f"Dependency lifecycle method '{method_name}' returned an "
            "awaitable. Use the asynchronous lifecycle manager for this "
            "dependency."
        )


class DependencyContainer:
    """Thread-safe container owning the application's dependencies."""

    def __init__(
        self,
        settings: AQESettings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._dependencies: EngineDependencies | None = None
        self._lock = Lock()

    @property
    def settings(self) -> AQESettings:
        """Return the configuration used by the container."""

        return self._settings

    @property
    def dependencies(self) -> EngineDependencies:
        """Return initialized dependencies.

        Raises:
            RuntimeError: If dependencies have not been initialized.
        """

        if self._dependencies is None:
            raise RuntimeError("AQE dependencies have not been initialized.")

        return self._dependencies

    def initialize(
        self,
        **dependencies: Any,
    ) -> EngineDependencies:
        """Initialize the shared dependency container.

        Example:

            container.initialize(
                database=db,
                event_bus=event_bus,
                broker_manager=broker_manager,
                market_feed=market_feed,
                risk_manager=risk_manager,
                execution_engine=execution_engine,
                portfolio_manager=portfolio_manager,
            )
        """

        with self._lock:
            if self._dependencies is not None:
                raise RuntimeError("AQE dependencies have already been initialized.")

            self._dependencies = EngineDependencies(
                settings=self._settings,
                **dependencies,
            )

            return self._dependencies

    def reset(self) -> None:
        """Reset the container.

        Primarily intended for testing and controlled application
        reinitialization.
        """

        with self._lock:
            self._dependencies = None


_default_container = DependencyContainer()


def get_container() -> DependencyContainer:
    """Return the process-wide AQE dependency container."""

    return _default_container


def get_engine_dependencies() -> EngineDependencies:
    """Return initialized process-wide engine dependencies."""

    return get_container().dependencies


def initialize_engine_dependencies(
    **dependencies: Any,
) -> EngineDependencies:
    """Initialize the process-wide AQE dependency container."""

    return get_container().initialize(**dependencies)


def reset_engine_dependencies() -> None:
    """Reset the process-wide dependency container."""

    get_container().reset()


@contextmanager
def dependency_scope(
    settings: AQESettings | None = None,
    **dependencies: Any,
) -> Iterator[EngineDependencies]:
    """Create a temporary dependency scope.

    This is particularly useful for unit and integration tests.

    Example:

        with dependency_scope(
            settings=test_settings,
            event_bus=test_event_bus,
            broker_manager=test_broker,
            market_feed=test_feed,
            risk_manager=test_risk,
            execution_engine=test_execution,
            portfolio_manager=test_portfolio,
        ) as deps:
            ...
    """

    container = DependencyContainer(settings=settings)
    deps = container.initialize(**dependencies)

    try:
        yield deps
    finally:
        try:
            deps.stop()
        finally:
            deps.close()


__all__ = [
    "DependencyContainer",
    "EngineDependencies",
    "Closeable",
    "Startable",
    "Stoppable",
    "dependency_scope",
    "get_container",
    "get_engine_dependencies",
    "initialize_engine_dependencies",
    "reset_engine_dependencies",
]
