from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from .orchestration import BacktestOrchestrator


class BacktestFactoryError(RuntimeError):
    """Raised when a backtest orchestrator cannot be constructed."""


BacktestOrchestratorBuilder = Callable[
    [Any],
    BacktestOrchestrator | Awaitable[BacktestOrchestrator],
]


class BacktestFactory:
    """
    Builds fully configured BacktestOrchestrator instances.

    The builder may be synchronous or asynchronous. This is required because
    historical market-data loading is asynchronous.
    """

    def __init__(
        self,
        *,
        orchestrator_builder: BacktestOrchestratorBuilder,
    ) -> None:
        if not callable(orchestrator_builder):
            raise TypeError("orchestrator_builder must be callable.")

        self._orchestrator_builder = orchestrator_builder

    async def create(
        self,
        config: Any,
    ) -> BacktestOrchestrator:
        """
        Build and return a BacktestOrchestrator.

        Supports both synchronous and asynchronous builders.
        """
        result = self._orchestrator_builder(config)

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(result, BacktestOrchestrator):
            raise TypeError(
                "Backtest orchestrator builder must return " "BacktestOrchestrator."
            )

        return result
