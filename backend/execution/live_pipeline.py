from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.broker.broker_manager import BrokerManager
from app.events import EventBus, event_bus
from risk.engine import RiskEngine

from .context_provider import RiskContextProvider
from .engine import ExecutionEngine
from .live_context_provider import LiveRiskContextProvider
from .signal_pipeline import SignalRiskExecutionPipeline


SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(slots=True)
class LivePipeline:
    """
    Runtime composition of the live trading pipeline.

        StrategySignalEvent
                ↓
        RiskContextProvider
                ↓
        RiskEngine
                ↓
        ExecutionEngine
                ↓
        BrokerManager
                ↓
        Broker

    The pipeline owns the signal → risk → execution flow.

    It does NOT own:
        - database connection lifecycle;
        - Redis connection lifecycle;
        - broker connection lifecycle;
        - FastAPI application lifecycle.

    Those remain owned by their respective infrastructure/runtime
    components.
    """

    broker_manager: BrokerManager
    risk_engine: RiskEngine
    context_provider: RiskContextProvider
    execution_engine: ExecutionEngine
    signal_pipeline: SignalRiskExecutionPipeline

    # ======================================================================
    # STATE
    # ======================================================================

    @property
    def started(self) -> bool:
        """
        Whether the signal → risk → execution pipeline is running.
        """

        return self.signal_pipeline.started

    @property
    def stats(self):
        """
        Runtime statistics exposed by the signal pipeline.
        """

        return self.signal_pipeline.stats

    # ======================================================================
    # LIFECYCLE
    # ======================================================================

    async def start(self) -> None:
        """
        Start the signal → risk → execution pipeline.

        Broker connectivity is intentionally not started here.
        AQEEngine controls the broker lifecycle.
        """

        await self.signal_pipeline.start()

    async def stop(self) -> None:
        """
        Stop the signal → risk → execution pipeline.
        """

        await self.signal_pipeline.stop()

    # ======================================================================
    # OBSERVABILITY
    # ======================================================================

    def snapshot(self) -> dict:
        """
        Return a runtime snapshot of the live pipeline.
        """

        return {
            "started": self.started,
            "signal_pipeline": self.signal_pipeline.snapshot(),
        }


# ============================================================================
# FACTORY
# ============================================================================


def create_live_pipeline(
    *,
    session_factory: SessionFactory,
    broker_manager: BrokerManager,
    risk_engine: RiskEngine,
    context_provider: LiveRiskContextProvider,
    bus: EventBus | None = None,
) -> LivePipeline:
    """
    Compose the production live trading pipeline.

    Dependency flow:

        StrategySignalEvent
                ↓
        SignalRiskExecutionPipeline
                ↓
        LiveRiskContextProvider
                ↓
        RiskEngine
                ↓
        ExecutionEngine
                ↓
        OrderRepository
                ↓
        BrokerManager
                ↓
        BrokerAdapter
                ↓
        Broker

    Database sessions are supplied as a factory rather than as one
    long-lived AsyncSession.

    This is important because the pipeline can process multiple
    strategy signals concurrently.

    Dependencies:

        session_factory
            SQLAlchemy async session factory used by:
                - LiveContextFactory callbacks;
                - ExecutionEngine;
                - OrderRepository operations.

        broker_manager
            Broker abstraction used by both live risk-context
            construction and order execution.

        risk_engine
            Evaluates strategy signals against the constructed
            RiskContext.

        context_provider
            Builds the RiskContext required by RiskEngine.

        bus
            AQE EventBus used for strategy signals and execution
            lifecycle events.

    No component is started or connected here.
    This function only performs dependency composition.
    """

    if not isinstance(context_provider, LiveRiskContextProvider):
        raise TypeError(
            "create_live_pipeline requires a LiveRiskContextProvider."
        )

    resolved_bus = bus or event_bus

    execution_engine = ExecutionEngine(
        session_factory=session_factory,
        broker_manager=broker_manager,
        bus=resolved_bus,
    )

    signal_pipeline = SignalRiskExecutionPipeline(
        risk_engine=risk_engine,
        execution_engine=execution_engine,
        context_provider=context_provider,
        bus=resolved_bus,
    )

    return LivePipeline(
        broker_manager=broker_manager,
        risk_engine=risk_engine,
        context_provider=context_provider,
        execution_engine=execution_engine,
        signal_pipeline=signal_pipeline,
    )