"""Live Strategy → Risk → Execution pipeline for AQE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.events.strategy import StrategySignalEvent

from .signal_pipeline import (
    SignalPipelineStats,
    SignalRiskExecutionPipeline,
)


@dataclass(slots=True)
class LivePipeline:
    """
    Runtime wrapper around the live Strategy → Risk → Execution pipeline.

    LivePipeline intentionally contains no trading logic of its own.

    The actual processing path is implemented by
    SignalRiskExecutionPipeline:

        StrategySignalEvent
            ↓
        RiskContextProvider
            ↓
        RiskEngine
            ↓
        RiskDecision
            ↓
        ExecutionEngine

    This wrapper exists so AQEEngine and ExecutionRuntime have a clear
    live-runtime component without duplicating pipeline logic.
    """

    signal_pipeline: SignalRiskExecutionPipeline

    # ==================================================================
    # PROPERTIES
    # ==================================================================

    @property
    def started(self) -> bool:
        """Return whether the live signal pipeline is started."""

        return self.signal_pipeline.started

    @property
    def stats(self) -> SignalPipelineStats:
        """Return live pipeline processing statistics."""

        return self.signal_pipeline.stats

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(self) -> None:
        """
        Start the live Strategy → Risk → Execution pipeline.

        The underlying SignalRiskExecutionPipeline subscribes to
        StrategySignalEvent on the shared EventBus.
        """

        await self.signal_pipeline.start()

    async def stop(self) -> None:
        """
        Stop the live Strategy → Risk → Execution pipeline.

        The underlying SignalRiskExecutionPipeline unsubscribes from
        StrategySignalEvent.
        """

        await self.signal_pipeline.stop()

    # ==================================================================
    # DIRECT PROCESSING
    # ==================================================================

    async def process(
        self,
        event: StrategySignalEvent,
    ) -> Any:
        """
        Process one StrategySignalEvent directly.

        This is useful for deterministic tests, replay, and diagnostics.

        Normal LIVE/PAPER operation should use EventBus delivery through
        ``start()``.
        """

        return await self.signal_pipeline.process(
            event,
        )

    # ==================================================================
    # SNAPSHOT
    # ==================================================================

    def snapshot(self) -> dict[str, Any]:
        """Return a lightweight live pipeline snapshot."""

        return self.signal_pipeline.snapshot()


__all__ = [
    "LivePipeline",
]
