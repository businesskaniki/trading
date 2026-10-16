from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OrderStatus
from app.events import EventBus, event_bus
from app.repositories.order_repository import OrderRepository

from .events import ExecutionCompletedEvent, ExecutionFailedEvent

logger = logging.getLogger(__name__)


class ExecutionResultConsumer:
    """
    Persists execution outcomes into the AQE order lifecycle.

    ExecutionEngine remains persistence-agnostic. It publishes execution
    events, and this consumer translates those events into AQE Order state.

    Lifecycle:

        ExecutionSubmittedEvent
                │
                ▼
        Broker execution
                │
                ├── success ──► ExecutionCompletedEvent
                │                    │
                │                    ▼
                │              AQE Order FILLED/PENDING
                │
                └── failure ──► ExecutionFailedEvent
                                     │
                                     ▼
                                AQE Order state

    The consumer does not create Positions. Position creation remains the
    responsibility of PositionSyncService because the broker position is
    the authoritative source for actual position state.

    Important failure semantics:

        broker_execution_outcome="rejected"
            -> OrderStatus.REJECTED

        broker_execution_outcome="unknown"
            -> OrderStatus.SUBMITTED when broker submission occurred

        execution_submitted=False
            -> preserve the current AQE order status

    A failed event is therefore not treated as a cancellation by default.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        bus: EventBus | None = None,
    ) -> None:
        self._repository = OrderRepository(db)
        self._bus = bus or event_bus
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return

        await self._bus.subscribe(
            ExecutionCompletedEvent,
            self.handle_completed,
        )

        await self._bus.subscribe(
            ExecutionFailedEvent,
            self.handle_failed,
        )

        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return

        await self._bus.unsubscribe(
            ExecutionCompletedEvent,
            self.handle_completed,
        )

        await self._bus.unsubscribe(
            ExecutionFailedEvent,
            self.handle_failed,
        )

        self._started = False

    # ------------------------------------------------------------------
    # Successful execution
    # ------------------------------------------------------------------

    async def handle_completed(
        self,
        event: ExecutionCompletedEvent,
    ) -> None:
        """
        Apply a successful broker execution to the corresponding AQE Order.
        """

        order = await self._find_order(event)

        if order is None:
            raise LookupError(
                "Unable to persist execution result because the AQE "
                "Order could not be located. "
                f"decision_id={event.decision_id}, "
                f"signal_id={event.signal_id}, "
                f"account_id={event.account_id}."
            )

        if event.order_id is not None:
            order.broker_order_id = event.order_id

        if event.execution_id is not None:
            order.broker_deal_id = event.execution_id

        if event.position_id is not None:
            order.broker_position_id = event.position_id

        if event.fill_price is not None:
            order.executed_price = event.fill_price

        if event.filled_quantity is not None:
            order.volume = event.filled_quantity

        mapped_status = self._map_success_status(event.status)

        if mapped_status is not None:
            order.status = mapped_status

        await self._repository.update(order)

        logger.info(
            "Execution result synchronized. "
            "decision_id=%s order_id=%s status=%s "
            "broker_order_id=%s broker_deal_id=%s broker_position_id=%s",
            event.decision_id,
            order.id,
            (
                order.status.value
                if isinstance(order.status, OrderStatus)
                else order.status
            ),
            order.broker_order_id,
            order.broker_deal_id,
            order.broker_position_id,
        )

    # ------------------------------------------------------------------
    # Failed execution
    # ------------------------------------------------------------------

    async def handle_failed(
        self,
        event: ExecutionFailedEvent,
    ) -> None:
        """
        Handle an execution failure event without inventing a broker
        outcome.

        The ExecutionEngine is authoritative for the immediate execution
        result. This consumer must not turn UNKNOWN into CANCELLED.

        The broker outcome is interpreted as follows:

            rejected
                The broker explicitly rejected the order.

            unknown
                The broker boundary was crossed but the final outcome
                could not be determined. The order remains SUBMITTED
                until reconciliation determines what actually happened.

            execution_submitted=False
                Broker submission did not occur. Preserve the current
                AQE order state rather than manufacturing a cancellation.
        """

        order = await self._find_order(event)

        if order is None:
            logger.warning(
                "Execution failure could not be associated with an AQE "
                "order. decision_id=%s account_id=%s symbol=%s",
                event.decision_id,
                event.account_id,
                event.symbol,
            )
            return

        next_status = self._failure_status(
            event=event,
            current_status=order.status,
        )

        # Never allow a failure event to overwrite a broker-confirmed
        # terminal/settled state that may already have been established
        # by execution completion or reconciliation.
        if order.status in {
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.PENDING,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }:
            next_status = order.status

        order.status = next_status

        order.comment = self._failure_comment(
            existing_comment=order.comment,
            error_message=event.message,
        )

        await self._repository.update(order)

        metadata = event.metadata or {}

        logger.info(
            "Execution failure synchronized. "
            "decision_id=%s order_id=%s status=%s "
            "broker_execution_outcome=%s execution_submitted=%s",
            event.decision_id,
            order.id,
            (
                order.status.value
                if isinstance(order.status, OrderStatus)
                else order.status
            ),
            metadata.get("broker_execution_outcome"),
            metadata.get("execution_submitted"),
        )

    # ------------------------------------------------------------------
    # Order lookup
    # ------------------------------------------------------------------

    async def _find_order(
        self,
        event: ExecutionCompletedEvent | ExecutionFailedEvent,
    ) -> Any | None:
        """
        Locate the AQE Order associated with the execution.

        The execution correlation ID is authoritative and is checked first.

        Broker identifiers are checked next once they are available.

        The final fallback uses account/symbol/strategy matching, but it
        refuses to select an order when multiple candidates exist.
        """

        # --------------------------------------------------------------
        # 1. Deterministic execution correlation
        # --------------------------------------------------------------

        order = await self._repository.get_by_execution_correlation_id(
            event.decision_id,
        )

        if order is not None:
            return order

        # --------------------------------------------------------------
        # 2. Broker identifiers
        # --------------------------------------------------------------

        if isinstance(event, ExecutionCompletedEvent):
            if event.order_id is not None:
                order = await self._repository.get_by_broker_order_id(
                    event.order_id,
                )
                if order is not None:
                    return order

            if event.execution_id is not None:
                order = await self._repository.get_by_broker_deal_id(
                    event.execution_id,
                )
                if order is not None:
                    return order

            if event.position_id is not None:
                order = await self._repository.get_by_broker_position_id(
                    event.position_id,
                )
                if order is not None:
                    return order

        # --------------------------------------------------------------
        # 3. Strict metadata fallback
        # --------------------------------------------------------------

        return await self._find_by_execution_metadata(event)

    async def _find_by_execution_metadata(
        self,
        event: ExecutionCompletedEvent | ExecutionFailedEvent,
    ) -> Any | None:
        """
        Fallback lookup using account/symbol/strategy attributes.

        This method deliberately does not guess an arbitrary order when
        multiple candidates exist.
        """

        orders = await self._repository.get_by_account(
            event.account_id,
        )

        candidates = [
            order for order in orders if self._order_matches_event(order, event)
        ]

        if len(candidates) == 1:
            return candidates[0]

        if not candidates:
            return None

        raise LookupError(
            "Multiple AQE Orders match execution event; refusing to "
            "select an order implicitly. "
            f"account_id={event.account_id}, "
            f"symbol={event.symbol}, "
            f"strategy_id={event.strategy_id}."
        )

    @staticmethod
    def _order_matches_event(
        order: Any,
        event: ExecutionCompletedEvent | ExecutionFailedEvent,
    ) -> bool:
        if getattr(order, "account_id", None) != event.account_id:
            return False

        symbol = getattr(
            getattr(order, "symbol", None),
            "name",
            None,
        )

        if symbol is None:
            return False

        if str(symbol).strip().upper() != event.symbol.strip().upper():
            return False

        strategy = getattr(order, "strategy", None)

        return (
            strategy is None
            or str(strategy) == str(event.strategy_id)
            or str(strategy) == str(event.strategy_name)
        )

    # ------------------------------------------------------------------
    # Status mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_success_status(
        status: str,
    ) -> OrderStatus | None:
        """
        Map the execution-layer completion status into the AQE Order
        lifecycle.

        Unknown completion statuses do not overwrite the current order
        state.
        """

        normalized = str(status).strip().upper()

        if normalized in {
            OrderStatus.FILLED.value,
            "EXECUTED",
            "COMPLETED",
        }:
            return OrderStatus.FILLED

        if normalized in {
            OrderStatus.PENDING.value,
            "PLACED",
            "ACCEPTED",
        }:
            return OrderStatus.PENDING

        if normalized in {
            OrderStatus.PARTIALLY_FILLED.value,
            "PARTIAL",
            "PARTIALLY EXECUTED",
        }:
            return OrderStatus.PARTIALLY_FILLED

        return None

    @staticmethod
    def _failure_status(
        *,
        event: ExecutionFailedEvent,
        current_status: OrderStatus,
    ) -> OrderStatus:
        """
        Determine the correct AQE lifecycle state for a failed execution
        event.

        A failed event is not proof that the broker rejected the order.

        Rules:

            rejected
                -> REJECTED

            unknown + execution submitted
                -> SUBMITTED

            execution not submitted
                -> preserve current state

            anything else
                -> preserve current state
        """

        metadata = event.metadata or {}

        execution_submitted = metadata.get(
            "execution_submitted",
        )

        broker_execution_outcome = metadata.get(
            "broker_execution_outcome",
        )

        if isinstance(broker_execution_outcome, str):
            broker_execution_outcome = broker_execution_outcome.strip().lower()

        # --------------------------------------------------------------
        # Explicit broker rejection.
        #
        # A broker rejection is definitive and therefore becomes
        # REJECTED. We do not require execution_submitted=True here,
        # because the rejection itself is the broker's definitive
        # response.
        # --------------------------------------------------------------

        if broker_execution_outcome == "rejected":
            return OrderStatus.REJECTED

        # --------------------------------------------------------------
        # Broker response was lost / final outcome is unknown.
        #
        # Only move to SUBMITTED when the execution boundary was
        # actually crossed.
        # --------------------------------------------------------------

        if broker_execution_outcome == "unknown":
            if execution_submitted is True:
                return OrderStatus.SUBMITTED

            return current_status

        # --------------------------------------------------------------
        # Broker was never reached.
        #
        # Never manufacture CANCELLED here.
        # --------------------------------------------------------------

        if execution_submitted is False:
            return current_status

        # --------------------------------------------------------------
        # Unknown/unclassified failure.
        #
        # Preserve the existing lifecycle state. A consumer must not
        # guess what happened at the broker.
        # --------------------------------------------------------------

        return current_status

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    @staticmethod
    def _failure_comment(
        existing_comment: str | None,
        error_message: str,
    ) -> str:
        base = (existing_comment or "").strip()

        suffix = f"Execution failed: {error_message}"

        if not base:
            return suffix[:255]

        separator = " | "
        available = 255 - len(separator) - len(suffix)

        if available <= 0:
            return suffix[:255]

        return f"{base[:available]}{separator}{suffix}"


__all__ = [
    "ExecutionResultConsumer",
]
