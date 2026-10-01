from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.schemas.execution import ExecutionOrder, OrderType

from .fill import BacktestFill, BacktestFillEngine
from .market import BacktestMarket


class PendingOrderStatus(StrEnum):
    """Lifecycle state of a simulated pending order."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class PendingBacktestOrder:
    """
    Simulated LIMIT or STOP order waiting for a market condition.

    A pending order belongs to one simulated account and may be
    attributed to one strategy.

    The order remains in this book until it is:
        - filled
        - cancelled
        - expired
    """

    order_id: UUID
    order: ExecutionOrder
    created_at: datetime

    status: PendingOrderStatus = PendingOrderStatus.PENDING

    filled_at: datetime | None = None
    cancelled_at: datetime | None = None

    fill: BacktestFill | None = None

    expiration: datetime | None = None

    strategy_id: str | None = None
    strategy_name: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.created_at = self._normalize_datetime(
            self.created_at,
        )

        if self.expiration is not None:
            self.expiration = self._normalize_datetime(
                self.expiration,
            )

        if self.order.order_type == OrderType.MARKET:
            raise ValueError("MARKET orders cannot be stored as pending orders.")

        if self.order.order_type not in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise ValueError(
                "Only LIMIT and STOP orders can be stored as "
                "pending backtest orders."
            )

        if self.expiration is not None:
            if self.expiration <= self.created_at:
                raise ValueError("Order expiration must be after order creation.")

        if self.strategy_id is not None:
            self.strategy_id = self.strategy_id.strip() or None

        if self.strategy_name is not None:
            self.strategy_name = self.strategy_name.strip() or None

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    @property
    def is_pending(self) -> bool:
        return self.status == PendingOrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        return self.status == PendingOrderStatus.FILLED

    @property
    def is_cancelled(self) -> bool:
        return self.status == PendingOrderStatus.CANCELLED

    @property
    def is_expired(self) -> bool:
        return self.status == PendingOrderStatus.EXPIRED

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


class BacktestPendingOrderBook:
    """
    Deterministic pending-order book for the backtest engine.

    Supported orders:
        - LIMIT
        - STOP

    MARKET orders bypass this book and are executed immediately.

    Responsibilities:
        - register pending orders
        - evaluate pending orders on market events
        - expire pending orders
        - cancel pending orders
        - retain lifecycle history

    It does not:
        - update account balance
        - create positions
        - perform risk checks
        - run strategies
        - communicate with live brokers
        - persist orders
    """

    def __init__(
        self,
        fill_engine: BacktestFillEngine,
    ) -> None:
        self.fill_engine = fill_engine

        self._orders: dict[
            UUID,
            PendingBacktestOrder,
        ] = {}

        self._current_time: datetime | None = None

    # ------------------------------------------------------------------
    # PROPERTIES
    # ------------------------------------------------------------------

    @property
    def current_time(self) -> datetime | None:
        """
        Return the last simulation timestamp processed by this order
        book.
        """

        return self._current_time

    @property
    def order_count(self) -> int:
        """Return the total number of retained orders."""

        return len(self._orders)

    @property
    def pending_count(self) -> int:
        """Return the number of currently pending orders."""

        return sum(1 for order in self._orders.values() if order.is_pending)

    # ------------------------------------------------------------------
    # REGISTRATION
    # ------------------------------------------------------------------

    def add(
        self,
        order: ExecutionOrder,
        *,
        created_at: datetime,
        order_id: UUID | None = None,
        expiration: datetime | None = None,
        strategy_id: str | None = None,
        strategy_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PendingBacktestOrder:
        """
        Register a LIMIT or STOP order.

        The order is not filled when registered. It becomes eligible
        for execution starting from its creation timestamp.
        """

        if order.order_type == OrderType.MARKET:
            raise ValueError("MARKET orders must be executed immediately.")

        if order.order_type not in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise ValueError(
                f"Unsupported pending order type: " f"{order.order_type!r}."
            )

        resolved_created_at = self._normalize_datetime(
            created_at,
        )

        resolved_id = order_id or uuid4()

        if resolved_id in self._orders:
            raise ValueError(f"Pending order '{resolved_id}' already exists.")

        if self._current_time is not None:
            if resolved_created_at < self._current_time:
                raise ValueError(
                    "Pending order creation time cannot move before "
                    "the current backtest time."
                )

        pending = PendingBacktestOrder(
            order_id=resolved_id,
            order=order,
            created_at=resolved_created_at,
            expiration=expiration,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            metadata=dict(metadata or {}),
        )

        self._orders[resolved_id] = pending

        return pending

    # ------------------------------------------------------------------
    # LOOKUPS
    # ------------------------------------------------------------------

    def get(
        self,
        order_id: UUID,
    ) -> PendingBacktestOrder:
        """Return one retained order by ID."""

        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise KeyError(f"Pending order '{order_id}' was not found.") from exc

    def all(self) -> list[PendingBacktestOrder]:
        """Return all retained orders."""

        return list(self._orders.values())

    def pending(self) -> list[PendingBacktestOrder]:
        """Return currently pending orders."""

        return [order for order in self._orders.values() if order.is_pending]

    def completed(self) -> list[PendingBacktestOrder]:
        """Return filled, cancelled, and expired orders."""

        return [order for order in self._orders.values() if not order.is_pending]

    def for_symbol(
        self,
        symbol: str,
    ) -> list[PendingBacktestOrder]:
        """
        Return pending orders for one normalized symbol.
        """

        normalized = self._normalize_symbol(symbol)

        return [
            order
            for order in self.pending()
            if self._normalize_symbol(order.order.symbol) == normalized
        ]

    def for_strategy(
        self,
        strategy_id: str,
    ) -> list[PendingBacktestOrder]:
        """
        Return retained orders belonging to one strategy.

        This is for reporting/attribution and does not change the
        shared account model.
        """

        normalized = strategy_id.strip()

        return [
            order for order in self._orders.values() if order.strategy_id == normalized
        ]

    # ------------------------------------------------------------------
    # PROCESSING
    # ------------------------------------------------------------------

    def process_market(
        self,
        market: BacktestMarket,
    ) -> list[PendingBacktestOrder]:
        """
        Evaluate all eligible pending orders against one market event.

        Processing is deterministic:

            1. advance simulation time
            2. expire eligible orders
            3. select matching-symbol pending orders
            4. sort by creation time then order ID
            5. ask BacktestFillEngine whether each order fills
            6. transition successfully filled orders

        The method does not mutate the portfolio. The caller owns the
        resulting fills and applies them through BacktestExecution.
        """

        if not isinstance(market, BacktestMarket):
            raise TypeError("process_market() requires a BacktestMarket.")

        current_time = self._normalize_datetime(
            market.timestamp,
        )

        if self._current_time is not None and current_time < self._current_time:
            raise ValueError(
                "Pending order book time cannot move backwards. "
                f"Current={self._current_time.isoformat()}, "
                f"requested={current_time.isoformat()}."
            )

        self._current_time = current_time

        # Orders that expire at the current timestamp are no longer
        # eligible for execution.
        self.expire(current_time)

        candidates = self.for_symbol(
            market.symbol,
        )

        candidates.sort(
            key=lambda item: (
                item.created_at,
                str(item.order_id),
            ),
        )

        triggered: list[PendingBacktestOrder] = []

        for pending in candidates:
            if not pending.is_pending:
                continue

            # The order cannot execute before it was created.
            if current_time < pending.created_at:
                continue

            # The expiration boundary is exclusive. An order at the
            # exact expiration timestamp has already been expired above.
            if pending.expiration is not None and current_time >= pending.expiration:
                continue

            fill = self.fill_engine.execute(
                order=pending.order,
                market=market,
                order_id=pending.order_id,
            )

            if not fill.filled:
                continue

            pending.status = PendingOrderStatus.FILLED
            pending.filled_at = current_time
            pending.fill = fill

            triggered.append(pending)

        return triggered

    # ------------------------------------------------------------------
    # CANCELLATION
    # ------------------------------------------------------------------

    def cancel(
        self,
        order_id: UUID,
        *,
        timestamp: datetime | None = None,
    ) -> PendingBacktestOrder:
        """
        Cancel a pending order.

        When no timestamp is supplied, the current simulated timestamp
        is used. If the simulation has not started yet, the order's
        creation timestamp is used. This keeps cancellation deterministic.
        """

        pending = self.get(order_id)

        if not pending.is_pending:
            raise ValueError(f"Order '{order_id}' is not pending.")

        cancellation_time = self._resolve_timestamp(
            timestamp,
            fallback=pending.created_at,
        )

        if cancellation_time < pending.created_at:
            raise ValueError("Cancellation time cannot be before order creation.")

        if pending.expiration is not None and cancellation_time >= pending.expiration:
            pending.status = PendingOrderStatus.EXPIRED
            pending.cancelled_at = cancellation_time

            return pending

        pending.status = PendingOrderStatus.CANCELLED
        pending.cancelled_at = cancellation_time

        return pending

    def cancel_symbol(
        self,
        symbol: str,
        *,
        timestamp: datetime | None = None,
    ) -> list[PendingBacktestOrder]:
        """Cancel all pending orders for one symbol."""

        normalized = self._normalize_symbol(symbol)

        cancelled: list[PendingBacktestOrder] = []

        for pending in list(self.pending()):
            if self._normalize_symbol(pending.order.symbol) != normalized:
                continue

            self.cancel(
                pending.order_id,
                timestamp=timestamp,
            )

            cancelled.append(pending)

        return cancelled

    def cancel_strategy(
        self,
        strategy_id: str,
        *,
        timestamp: datetime | None = None,
    ) -> list[PendingBacktestOrder]:
        """Cancel all pending orders belonging to one strategy."""

        normalized = strategy_id.strip()

        cancelled: list[PendingBacktestOrder] = []

        for pending in list(self.pending()):
            if pending.strategy_id != normalized:
                continue

            self.cancel(
                pending.order_id,
                timestamp=timestamp,
            )

            cancelled.append(pending)

        return cancelled

    def cancel_all(
        self,
        *,
        timestamp: datetime | None = None,
    ) -> list[PendingBacktestOrder]:
        """Cancel every currently pending order."""

        cancelled: list[PendingBacktestOrder] = []

        for pending in list(self.pending()):
            self.cancel(
                pending.order_id,
                timestamp=timestamp,
            )

            cancelled.append(pending)

        return cancelled

    # ------------------------------------------------------------------
    # EXPIRATION
    # ------------------------------------------------------------------

    def expire(
        self,
        timestamp: datetime,
    ) -> list[PendingBacktestOrder]:
        """
        Expire orders whose expiration timestamp has been reached.

        Expiration is inclusive:

            current_time >= expiration
        """

        normalized = self._normalize_datetime(
            timestamp,
        )

        expired: list[PendingBacktestOrder] = []

        for pending in self.pending():
            if pending.expiration is None:
                continue

            if normalized < pending.expiration:
                continue

            pending.status = PendingOrderStatus.EXPIRED
            pending.cancelled_at = normalized

            expired.append(pending)

        return expired

    # ------------------------------------------------------------------
    # MAINTENANCE
    # ------------------------------------------------------------------

    def remove_completed(self) -> int:
        """
        Remove completed orders from the retained order book.

        Use this only when another component retains historical order
        results.
        """

        completed_ids = [order.order_id for order in self.completed()]

        for order_id in completed_ids:
            del self._orders[order_id]

        return len(completed_ids)

    def clear(self) -> None:
        """Clear all pending and historical orders."""

        self._orders.clear()
        self._current_time = None

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        """
        Return a serializable representation of every retained order.
        """

        return [self._serialize_order(order) for order in self.all()]

    @staticmethod
    def _serialize_order(
        pending: PendingBacktestOrder,
    ) -> dict[str, Any]:
        order = pending.order

        return {
            "order_id": str(pending.order_id),
            "account_id": (
                str(order.account_id) if order.account_id is not None else None
            ),
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "volume": order.volume,
            "price": order.price,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "deviation": order.deviation,
            "magic_number": order.magic_number,
            "comment": order.comment,
            "status": pending.status.value,
            "created_at": pending.created_at,
            "filled_at": pending.filled_at,
            "cancelled_at": pending.cancelled_at,
            "expiration": pending.expiration,
            "strategy_id": pending.strategy_id,
            "strategy_name": pending.strategy_name,
            "metadata": dict(pending.metadata),
            "fill_id": (
                str(pending.fill.fill_id) if pending.fill is not None else None
            ),
            "fill_price": (pending.fill.price if pending.fill is not None else None),
            "commission": (
                pending.fill.commission if pending.fill is not None else Decimal("0")
            ),
        }

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        normalized = str(symbol).strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    def _resolve_timestamp(
        self,
        timestamp: datetime | None,
        *,
        fallback: datetime,
    ) -> datetime:
        if timestamp is not None:
            normalized = self._normalize_datetime(
                timestamp,
            )
        elif self._current_time is not None:
            normalized = self._current_time
        else:
            normalized = fallback

        if self._current_time is not None and normalized < self._current_time:
            raise ValueError(
                "Order timestamp cannot move backwards from the "
                "current backtest time."
            )

        return normalized
