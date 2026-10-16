"""Coordinate the runtime Strategy → Risk → Execution pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.events import EventBus, event_bus
from app.events.strategy import StrategySignalEvent
from app.schemas.execution import ExecutionStatus
from risk.engine import RiskEngine
from risk.models import RiskContext, RiskDecision
from strategies.core.signal import TradingSignal

from .context_provider import RiskContextProvider
from .engine import ExecutionEngine
from .exceptions import ExecutionRejectedError

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

    # Confirmed complete executions only.
    execution_successes: int = 0

    # Legitimate outcomes that are not complete executions.
    execution_placements: int = 0
    execution_partial_fills: int = 0
    execution_unresolved: int = 0
    execution_not_submitted: int = 0
    execution_rejections: int = 0

    # Unexpected execution exceptions or unsuccessful results.
    execution_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return a serializable snapshot of all pipeline counters."""
        return {
            "received": self.received,
            "context_failures": self.context_failures,
            "risk_evaluations": self.risk_evaluations,
            "risk_rejections": self.risk_rejections,
            "approved": self.approved,
            "execution_successes": self.execution_successes,
            "execution_placements": self.execution_placements,
            "execution_partial_fills": self.execution_partial_fills,
            "execution_unresolved": self.execution_unresolved,
            "execution_not_submitted": self.execution_not_submitted,
            "execution_rejections": self.execution_rejections,
            "execution_failures": self.execution_failures,
        }


class SignalRiskExecutionPipeline:
    """Coordinate strategy signals, risk evaluation, and execution.

    StrategySignalEvent
            ↓
    RiskContextProvider
            ↓
        RiskEngine
            ↓
        RiskDecision
            ↓
      ExecutionEngine
            ↓
        BrokerManager

    This component receives signals, constructs the risk context,
    evaluates risk, and forwards approved decisions to the execution
    engine. It does not persist orders or communicate directly with
    the broker.

    Execution outcomes are tracked separately:
        SUCCESS          confirmed complete execution
        PLACED           order accepted/placed; fill not necessarily complete
        PARTIALLY_FILLED confirmed partial execution
        UNKNOWN          outcome requires reconciliation
        NOT_SUBMITTED    broker submission did not occur
        REJECTED         explicit execution rejection
        FAILED           unsuccessful or legacy failure result
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
        self._event_bus = bus if bus is not None else event_bus

        self._started = False
        self._stats = SignalPipelineStats()

    @property
    def started(self) -> bool:
        """Return whether the pipeline is subscribed to strategy signals."""
        return self._started

    @property
    def stats(self) -> SignalPipelineStats:
        """Return the current pipeline statistics."""
        return self._stats

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable runtime snapshot."""
        return {
            "started": self._started,
            "stats": self._stats.as_dict(),
        }

    async def start(self) -> None:
        """Subscribe to StrategySignalEvent; repeated calls are safe."""
        if self._started:
            return

        await self._event_bus.subscribe(
            StrategySignalEvent,
            self._handle_signal,
        )
        self._started = True

        logger.info("Signal risk execution pipeline started.")

    async def stop(self) -> None:
        """Unsubscribe from StrategySignalEvent; repeated calls are safe."""
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
        """Process a signal directly, for tests and controlled callers."""
        return await self._handle_signal(event)

    async def _handle_signal(
        self,
        event: StrategySignalEvent,
    ) -> RiskDecision | None:
        """Process one signal through context construction, risk, and execution."""
        if not isinstance(event, StrategySignalEvent):
            logger.error(
                "Signal pipeline received invalid event: expected=%s received=%s",
                StrategySignalEvent.__name__,
                type(event).__name__,
            )
            return None

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

        # 1. Build the risk context.
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

        # 2. Evaluate the signal through the Risk Engine.
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

        if decision.approved and decision.rejected:
            logger.error(
                "Risk Engine returned an inconsistent decision: "
                "signal_id=%s decision_id=%s",
                signal.signal_id,
                decision.decision_id,
            )
            return decision

        # 3. Rejected signals must never reach execution.
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
                "Risk Engine returned neither an approved nor rejected "
                "decision: signal_id=%s decision_id=%s status=%s",
                signal.signal_id,
                decision.decision_id,
                getattr(decision.status, "value", decision.status),
            )
            return decision

        # 4. The decision has been approved; proceed to execution.
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

        except ExecutionRejectedError:
            # An explicit rejection is a distinct outcome from an
            # unexpected execution exception.
            self._stats.execution_rejections += 1
            logger.warning(
                "Execution rejected: signal_id=%s decision_id=%s "
                "strategy_id=%s symbol=%s",
                signal.signal_id,
                decision.decision_id,
                signal.strategy_id,
                signal.symbol,
                exc_info=True,
            )
            return decision

        except Exception:
            self._stats.execution_failures += 1
            logger.exception(
                "Execution Engine raised an exception: "
                "signal_id=%s decision_id=%s strategy_id=%s symbol=%s",
                signal.signal_id,
                decision.decision_id,
                signal.strategy_id,
                signal.symbol,
            )
            return decision

        execution_status = getattr(result, "status", None)

        # 5. Classify outcomes accurately. A placed order or partial fill
        # is a legitimate broker outcome, not a generic execution failure.
        if execution_status is ExecutionStatus.SUCCESS:
            self._stats.execution_successes += 1
            logger.info(
                "Risk-approved signal fully executed: "
                "signal_id=%s decision_id=%s strategy_id=%s symbol=%s",
                signal.signal_id,
                decision.decision_id,
                signal.strategy_id,
                signal.symbol,
            )

        elif execution_status is ExecutionStatus.PLACED:
            self._stats.execution_placements += 1
            logger.info(
                "Broker accepted/placed the order; complete fill is not "
                "confirmed: signal_id=%s decision_id=%s symbol=%s "
                "broker_order_id=%s",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                getattr(result, "broker_order_id", None),
            )

        elif execution_status is ExecutionStatus.PARTIALLY_FILLED:
            self._stats.execution_partial_fills += 1
            logger.warning(
                "Order partially filled; remaining volume requires "
                "tracking/reconciliation: signal_id=%s decision_id=%s "
                "symbol=%s executed_volume=%s requested_volume=%s "
                "broker_order_id=%s",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                getattr(result, "volume", None),
                getattr(result, "requested_volume", None),
                getattr(result, "broker_order_id", None),
            )

        elif execution_status is ExecutionStatus.UNKNOWN:
            self._stats.execution_unresolved += 1
            logger.warning(
                "Broker outcome is unknown; reconciliation is required: "
                "signal_id=%s decision_id=%s symbol=%s "
                "broker_order_id=%s",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                getattr(result, "broker_order_id", None),
            )

        elif execution_status is ExecutionStatus.NOT_SUBMITTED:
            self._stats.execution_not_submitted += 1
            logger.warning(
                "Broker confirms the order was not submitted: "
                "signal_id=%s decision_id=%s symbol=%s. "
                "Any retry must use the same decision correlation and "
                "must verify the persisted order state.",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
            )

        elif execution_status is ExecutionStatus.REJECTED:
            self._stats.execution_rejections += 1
            logger.warning(
                "Broker rejected the order: signal_id=%s decision_id=%s "
                "symbol=%s message=%s",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                getattr(result, "message", None),
            )

        elif execution_status is ExecutionStatus.FAILED:
            self._stats.execution_failures += 1
            logger.error(
                "Broker execution returned FAILED: "
                "signal_id=%s decision_id=%s symbol=%s message=%s",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                getattr(result, "message", None),
            )

        else:
            self._stats.execution_failures += 1
            logger.error(
                "Execution Engine returned an unknown or invalid status: "
                "signal_id=%s decision_id=%s symbol=%s status=%r",
                signal.signal_id,
                decision.decision_id,
                signal.symbol,
                execution_status,
            )

        # The risk decision remains useful regardless of whether the
        # broker completed, placed, partially filled, or rejected the order.
        return decision

    async def _build_context(
        self,
        signal: TradingSignal,
    ) -> RiskContext:
        """Build and verify a RiskContext for the original signal."""
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

        context_signal = context.signal

        if context_signal.signal_id != signal.signal_id:
            raise SignalContextError(
                "RiskContext contains a different signal. "
                f"expected={signal.signal_id}, "
                f"received={context_signal.signal_id}."
            )

        if context_signal.strategy_id != signal.strategy_id:
            raise SignalContextError(
                "RiskContext contains a signal belonging to a different "
                f"strategy. expected={signal.strategy_id!r}, "
                f"received={context_signal.strategy_id!r}."
            )

        if context_signal.symbol != signal.symbol:
            raise SignalContextError(
                "RiskContext contains a signal for a different symbol. "
                f"expected={signal.symbol!r}, "
                f"received={context_signal.symbol!r}."
            )

        return context


__all__ = [
    "SignalPipelineError",
    "SignalContextError",
    "SignalPipelineStats",
    "SignalRiskExecutionPipeline",
]
