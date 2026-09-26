from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.order_repository import OrderRepository
from app.events import EventBus, event_bus
from app.schemas.execution import ExecutionStatus
from .events import ExecutionCompletedEvent, ExecutionFailedEvent


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

        update_data: dict[str, Any] = {}

        if event.order_id is not None:
            update_data["broker_order_id"] = event.order_id

        if event.execution_id is not None:
            update_data["broker_deal_id"] = event.execution_id

        if event.position_id is not None:
            update_data["broker_position_id"] = event.position_id

        if event.fill_price is not None:
            update_data["executed_price"] = event.fill_price

        if event.filled_quantity is not None:
            update_data["volume"] = event.filled_quantity

        status = self._map_success_status(event.status)

        if status is not None:
            update_data["status"] = status

        if update_data:
            await self._repository.update(
                order.id,
                **update_data,
            )

        await self._repository.commit()

    async def handle_failed(
        self,
        event: ExecutionFailedEvent,
    ) -> None:
        """
        Record an execution failure against the corresponding AQE Order.

        A failed execution does not create a Position.
        """

        order = await self._find_order(event)

        if order is None:
            raise LookupError(
                "Unable to persist execution failure because the AQE "
                "Order could not be located. "
                f"decision_id={event.decision_id}, "
                f"signal_id={event.signal_id}, "
                f"account_id={event.account_id}."
            )

        metadata = dict(getattr(order, "metadata", {}) or {})

        metadata["execution_error"] = {
            "error_type": event.error_type,
            "error_message": event.error_message,
            "event_id": str(event.event_id),
            "occurred_at": event.occurred_at.isoformat(),
        }

        await self._repository.update(
            order.id,
            status=self._failure_status(),
            comment=self._failure_comment(
                order.comment,
                event.error_message,
            ),
        )

        await self._repository.commit()

    async def _find_order(
        self,
        event: ExecutionCompletedEvent | ExecutionFailedEvent,
    ):
        """
        Locate the AQE Order associated with the execution.

        Broker identifiers are preferred once available. The decision ID
        remains the execution correlation identifier but is not assumed to
        be a database Order primary key.
        """

        if isinstance(event, ExecutionCompletedEvent):
            if event.order_id is not None:
                order = await self._repository.get_by_broker_order(
                    event.order_id
                )
                if order is not None:
                    return order

            if event.execution_id is not None:
                order = await self._repository.get_by_broker_deal(
                    event.execution_id
                )
                if order is not None:
                    return order

            if event.position_id is not None:
                order = await self._repository.get_by_broker_position(
                    event.position_id
                )
                if order is not None:
                    return order

        return await self._find_by_execution_metadata(event)

    async def _find_by_execution_metadata(
        self,
        event: ExecutionCompletedEvent | ExecutionFailedEvent,
    ):
        """
        Fallback lookup using the account/symbol/strategy execution
        correlation available to the consumer.

        This method deliberately does not guess an arbitrary order when
        multiple candidates exist.
        """

        orders = await self._repository.get_by_account(
            event.account_id
        )

        candidates = [
            order
            for order in orders
            if self._order_matches_event(order, event)
        ]

        if len(candidates) == 1:
            return candidates[0]

        if not candidates:
            return None

        # More than one matching order means that selecting one would be
        # unsafe and could attach a broker execution to the wrong order.
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

        symbol = getattr(getattr(order, "symbol", None), "name", None)

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

    @staticmethod
    def _map_success_status(
        status: str,
    ) -> ExecutionStatus | None:
        normalized = str(status).upper()

        if normalized in {
            ExecutionStatus.FILLED.value,
            "EXECUTED",
            "COMPLETED",
        }:
            return ExecutionStatus.FILLED

        if normalized in {
            ExecutionStatus.PENDING.value,
            "PLACED",
            "ACCEPTED",
        }:
            return ExecutionStatus.PENDING

        return None

    @staticmethod
    def _failure_status() -> ExecutionStatus:
        """
        Execution failures represent an order that did not successfully
        execute.

        The existing AQE order lifecycle uses CANCELLED for this terminal
        state.
        """

        return ExecutionStatus.CANCELLED

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