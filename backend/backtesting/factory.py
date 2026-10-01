"""Factory for constructing fully configured AQE backtest orchestrators."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .engine import BacktestConfig
from .orchestration import BacktestOrchestrator

logger = logging.getLogger(__name__)


class BacktestFactoryError(RuntimeError):
    """Raised when a backtest orchestrator cannot be constructed."""


class BacktestCompositionProtocol(Protocol):
    """
    Runtime-independent contract required from a backtest composition.

    The concrete BacktestComposition implementation lives in
    ``backtesting.composition`` and does not need to be imported here.
    This prevents a composition ↔ factory circular import.
    """

    def build(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator | Awaitable[BacktestOrchestrator]:
        """Build a fully configured backtest orchestrator."""


BacktestOrchestratorBuilder = Callable[
    [BacktestConfig],
    BacktestOrchestrator | Awaitable[BacktestOrchestrator],
]


class BacktestFactory:
    """
    Construct fully configured BacktestOrchestrator instances.

    The factory is the application-level construction boundary for the
    backtesting runtime.

    Dependency composition remains owned by BacktestComposition:

        BacktestConfig
              │
              ▼
        BacktestComposition
              │
              ├── account
              ├── strategies
              ├── symbols
              ├── symbol specifications
              ├── timeframes
              ├── historical market data
              ├── RiskEngine
              ├── BacktestEngine
              └── BacktestOrchestrator
              │
              ▼
        BacktestFactory
              │
              ▼
        BacktestOrchestrator

    The factory deliberately does not import BacktestComposition at
    runtime. The concrete composition object is injected into the
    factory, which avoids a circular import between the two modules.

    A direct orchestrator builder can also be injected for tests or
    specialized integrations.
    """

    def __init__(
        self,
        *,
        composition: BacktestCompositionProtocol | None = None,
        orchestrator_builder: BacktestOrchestratorBuilder | None = None,
    ) -> None:
        """
        Initialize the backtest factory.

        Parameters
        ----------
        composition:
            Concrete backtest composition object exposing:

                build(config)

            The concrete class is intentionally represented by a
            protocol so this module does not import ``composition.py``.

        orchestrator_builder:
            Optional explicit builder. When supplied, it takes precedence
            over ``composition``.

        At least one construction source must be supplied.
        """

        if (
            composition is None
            and orchestrator_builder is None
        ):
            raise TypeError(
                "BacktestFactory requires either "
                "composition or orchestrator_builder."
            )

        if (
            composition is not None
            and not callable(
                getattr(
                    composition,
                    "build",
                    None,
                )
            )
        ):
            raise TypeError(
                "composition must expose a callable build(config) "
                "method."
            )

        if (
            orchestrator_builder is not None
            and not callable(orchestrator_builder)
        ):
            raise TypeError(
                "orchestrator_builder must be callable."
            )

        self._composition = composition

        if orchestrator_builder is not None:
            self._orchestrator_builder = (
                orchestrator_builder
            )
        else:
            self._orchestrator_builder = (
                self._build_from_composition
            )

    # ==================================================================
    # CREATE
    # ==================================================================

    async def create(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Build and return a fully configured BacktestOrchestrator.

        The factory supports both synchronous and asynchronous builders.

        Construction failures are wrapped in BacktestFactoryError while
        preserving the original exception as the chained cause.
        """

        if not isinstance(
            config,
            BacktestConfig,
        ):
            raise TypeError(
                "config must be an instance of BacktestConfig."
            )

        try:
            result = self._orchestrator_builder(
                config,
            )

            if inspect.isawaitable(result):
                result = await result

        except Exception as exc:
            logger.exception(
                "Failed to construct backtest orchestrator. "
                "account_id=%s user_id=%s",
                getattr(
                    config,
                    "account_id",
                    None,
                ),
                getattr(
                    config,
                    "user_id",
                    None,
                ),
            )

            raise BacktestFactoryError(
                "Failed to construct the backtest orchestrator: "
                f"{exc}"
            ) from exc

        if not isinstance(
            result,
            BacktestOrchestrator,
        ):
            error = (
                "Backtest orchestrator builder returned an invalid "
                f"object of type {type(result).__name__}."
            )

            logger.error(
                "%s account_id=%s user_id=%s",
                error,
                getattr(
                    config,
                    "account_id",
                    None,
                ),
                getattr(
                    config,
                    "user_id",
                    None,
                ),
            )

            raise BacktestFactoryError(
                error,
            )

        return result

    # ==================================================================
    # COMPOSITION
    # ==================================================================

    async def _build_from_composition(
        self,
        config: BacktestConfig,
    ) -> BacktestOrchestrator:
        """
        Delegate construction to the injected composition.

        No concrete BacktestComposition import is required here.
        """

        composition = self._composition

        if composition is None:
            raise BacktestFactoryError(
                "No BacktestComposition is configured."
            )

        build_method: Any = getattr(
            composition,
            "build",
            None,
        )

        if not callable(build_method):
            raise BacktestFactoryError(
                "Configured backtest composition does not expose "
                "a callable build(config) method."
            )

        result = build_method(
            config,
        )

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(
            result,
            BacktestOrchestrator,
        ):
            raise BacktestFactoryError(
                "BacktestComposition.build(config) returned an "
                f"invalid object of type {type(result).__name__}."
            )

        return result


__all__ = [
    "BacktestCompositionProtocol",
    "BacktestFactory",
    "BacktestFactoryError",
    "BacktestOrchestratorBuilder",
]