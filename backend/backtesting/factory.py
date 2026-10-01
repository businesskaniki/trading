
"""Factory for constructing fully configured AQE backtest orchestrators."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable

from .engine import BacktestConfig
from .orchestration import BacktestOrchestrator

logger = logging.getLogger(__name__)


class BacktestFactoryError(RuntimeError):
    """Raised when a backtest orchestrator cannot be constructed."""


BacktestOrchestratorBuilder = Callable[
    [BacktestConfig],
    BacktestOrchestrator | Awaitable[BacktestOrchestrator],
]


class BacktestFactory:
    """
    Construct fully configured BacktestOrchestrator instances.

    The factory delegates dependency composition to an injected builder.

    The builder is responsible for resolving and assembling:

        account
            ↓
        active strategies
            ↓
        selected symbols
            ↓
        required timeframes
            ↓
        historical market data
            ↓
        RiskEngine
            ↓
        BacktestEngine
            ↓
        BacktestOrchestrator

    The builder may be synchronous or asynchronous because the
    composition process normally includes asynchronous database
    queries and historical market-data loading.
    """

    def __init__(
        self,
        *,
        orchestrator_builder: BacktestOrchestratorBuilder,
    ) -> None:
        if not callable(orchestrator_builder):
            raise TypeError(
                "orchestrator_builder must be callable."
            )

        self._orchestrator_builder = orchestrator_builder

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

        The original construction exception is preserved as the chained
        cause and logged with its complete traceback. This is important
        because composition may fail due to database configuration,
        strategy configuration, symbol resolution, RiskEngine wiring,
        or BacktestOrchestrator construction.
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


__all__ = [
    "BacktestFactory",
    "BacktestFactoryError",
    "BacktestOrchestratorBuilder",
]
