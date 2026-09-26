from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.events import EventBus, event_bus
from app.events.strategy import StrategySignalEvent
from risk.engine import RiskEngine
from risk.models import RiskContext, RiskDecision
from strategies.core.signal import TradingSignal

from .context_provider import RiskContextProvider
from .engine import ExecutionEngine

logger = logging.getLogger(__name__)


class SignalPipelineError(Exception):
    """Base exception for signal pipeline failures."""


class SignalContextError(SignalPipelineError):
    """Raised when a valid RiskContext cannot be constructed."""


@dataclass(slots=True)
class SignalPipelineStats:
    """Runtime statistics for the signal → risk → execution pipeline."""

    received: int = 0
    context_failures: int = 0
    risk_evaluations: int = 0
    risk_rejections: int = 0
    approved: int = 0
    execution_successes: int = 0
    execution_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "context_failures": self.context_failures,
            "risk_evaluations": self.risk_evaluations,
            "risk_rejections": self.risk_rejections,
            "approved": self.approved,
            "execution_successes": self.execution_successes,
            "execution_failures": self.execution_failures,
        }


class SignalRiskExecutionPipeline:
    """
    Coordinates:

        StrategySignalEvent
                ↓
        RiskContextProvider
                ↓
            RiskEngine
                ↓
          RiskDecision
                ↓
         ExecutionEngine

    This is the primary runtime path from strategy intent to execution.

    Responsibilities:
        - receive StrategySignalEvent
        - construct RiskContext
        - evaluate the signal through RiskEngine
        - reject execution when RiskEngine rejects the signal
        - forward approved RiskDecision objects to ExecutionEngine
        - isolate individual signal failures
        - maintain runtime statistics

    This component does NOT:
        - generate signals
        - calculate risk itself
        - calculate position size itself
        - modify RiskDecision objects
        - communicate directly with MT5
        - communicate directly with Redis
        - write to PostgreSQL
    """

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        execution_engine: ExecutionEngine,
        context_provider: RiskContextProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine
        self._context_provider = context_provider
        self._event_bus = bus or event_bus

        self._started = False
        self._stats = SignalPipelineStats()

    @property
    def started(self) -> bool:
        """Return whether the pipeline is subscribed to strategy signals."""

        return self._started

    @property
    def stats(self) -> SignalPipelineStats:
        """Return the live pipeline statistics object."""

        return self._stats

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable runtime snapshot."""

        return {
            "started": self._started,
            "stats": self._stats.as_dict(),
        }

    async def start(self) -> None:
        """
        Subscribe to StrategySignalEvent.

        Starting an already-running pipeline is intentionally idempotent.
        """

        if self._started:
            return

        await self._event_bus.subscribe(
            StrategySignalEvent,
            self._handle_signal,
        )

        self._started = True

        logger.info("Signal risk execution pipeline started.")

    async def stop(self) -> None:
        """
        Unsubscribe from StrategySignalEvent.

        Stopping an already-stopped pipeline is intentionally idempotent.
        """

        if not self._started:
            return

        await self._event_bus.unsubscribe(
            StrategySignalEvent,
            self._handle_signal,
        )

        self._started = False

        logger.info("Signal risk execution pipeline stopped.")

    async def process(
        self,
        event: StrategySignalEvent,
    ) -> RiskDecision | None:
        """
        Process one strategy signal directly.

        This method is useful for deterministic tests and for callers
        that already have a StrategySignalEvent.

        Returns:
            Approved or rejected RiskDecision.

        Returns None only when context construction fails before the
        Risk Engine can evaluate the signal.
        """

        return await self._handle_signal(event)

    async def _handle_signal(
        self,
        event: StrategySignalEvent,
    ) -> RiskDecision | None:
        """
        Execute the complete signal → risk → execution flow.

        Individual signal failures are isolated so that one malformed
        signal, unavailable account, risk failure, or broker execution
        failure cannot terminate the EventBus subscription.
        """

        signal = event.signal

        self._stats.received += 1

        logger.info(
            "Processing strategy signal: "
            "signal_id=%s strategy_id=%s strategy=%s "
            "symbol=%s timeframe=%s direction=%s type=%s",
            signal.signal_id,
            signal.strategy_id,
            signal.strategy_name,
            signal.symbol,
            signal.timeframe.value,
            signal.direction.value,
            signal.signal_type.value,
        )

        try:
            context = await self._build_context(signal)

        except SignalContextError:
            self._stats.context_failures += 1

            logger.exception(
                "Unable to construct RiskContext: "
                "signal_id=%s strategy_id=%s symbol=%s",
                signal.signal_id,
                signal.strategy_id,
                signal.symbol,
            )

            return None

        try:
            self._stats.risk_evaluations += 1

            decision = self._risk_engine.evaluate(context)

        except Exception:
            logger.exception(
                "Risk Engine evaluation failed: "
                "signal_id=%s strategy_id=%s symbol=%s",
                signal.signal_id,
                signal.strategy_id,
                signal.symbol,
            )

            return None

        if not isinstance(decision, RiskDecision):
            logger.error(
                "Risk Engine returned an invalid decision: "
                "signal_id=%s expected=RiskDecision received=%s",
                signal.signal_id,
                type(decision).__name__,
            )

            return None

        if decision.rejected:
            self._stats.risk_rejections += 1

            logger.info(
                "Strategy signal rejected by Risk Engine: "
                "signal_id=%s strategy_id=%s symbol=%s "
                "reason=%s message=%s",
                signal.signal_id,
                signal.strategy_id,
                signal.symbol,
                decision.rejection_reason,
                decision.message,
            )

            return decision

        if not decision.approved:
            logger.error(
                "Risk Engine returned a decision that is neither "
                "approved nor rejected: "
                "signal_id=%s decision_id=%s status=%s",
                signal.signal_id,
                decision.decision_id,
                decision.status.value,
            )

            return decision

        self._stats.approved += 1

        logger.info(
            "Strategy signal approved by Risk Engine: "
            "signal_id=%s decision_id=%s strategy_id=%s "
            "symbol=%s position_size=%s",
            signal.signal_id,
            decision.decision_id,
            signal.strategy_id,
            signal.symbol,
            decision.position_size,
        )

        try:
            result = await self._execution_engine.execute(decision)

        except Exception:
            self._stats.execution_failures += 1

            logger.exception(
                "Execution Engine failed: "
                "signal_id=%s decision_id=%s strategy_id=%s symbol=%s",
                signal.signal_id,
                decision.decision_id,
                signal.strategy_id,
                signal.symbol,
            )

            return decision

        self._stats.execution_successes += 1

        logger.info(
            "Risk-approved signal executed successfully: "
            "signal_id=%s decision_id=%s strategy_id=%s "
            "symbol=%s execution_status=%s",
            signal.signal_id,
            decision.decision_id,
            signal.strategy_id,
            signal.symbol,
            getattr(result, "status", None),
        )

        return decision

    async def _build_context(
        self,
        signal: TradingSignal,
    ) -> RiskContext:
        """
        Build and validate the RiskContext for a strategy signal.
        """

        try:
            context = await self._context_provider.build(signal)

        except Exception as exc:
            raise SignalContextError(
                "Unable to build RiskContext for "
                f"signal_id={signal.signal_id}, "
                f"strategy_id={signal.strategy_id}, "
                f"symbol={signal.symbol}."
            ) from exc

        if not isinstance(context, RiskContext):
            raise SignalContextError(
                "RiskContext provider returned an invalid object. "
                f"Expected RiskContext, got {type(context).__name__}."
            )

        if context.signal.signal_id != signal.signal_id:
            raise SignalContextError(
                "RiskContext contains a different signal. "
                f"expected={signal.signal_id}, "
                f"received={context.signal.signal_id}."
            )

        if context.signal.strategy_id != signal.strategy_id:
            raise SignalContextError(
                "RiskContext contains a signal belonging to a different "
                f"strategy. expected={signal.strategy_id!r}, "
                f"received={context.signal.strategy_id!r}."
            )

        if context.signal.symbol != signal.symbol:
            raise SignalContextError(
                "RiskContext contains a signal for a different symbol. "
                f"expected={signal.symbol!r}, "
                f"received={context.signal.symbol!r}."
            )

        return context
