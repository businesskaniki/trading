from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.schemas.execution import ExecutionOrder, OrderType

from .fill import BacktestFill, BacktestFillEngine, BacktestMarket


class PendingOrderStatus(StrEnum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class PendingBacktestOrder:
    """
    An ExecutionOrder waiting for a future market condition.

    MARKET orders should never normally enter this book because
    they are executable immediately. LIMIT and STOP orders can remain
    pending across multiple candles.
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

    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.created_at = self._normalize_datetime(self.created_at)

        if self.expiration is not None:
            self.expiration = self._normalize_datetime(self.expiration)

        if self.order.order_type == OrderType.MARKET:
            raise ValueError("MARKET orders cannot be stored as pending orders.")

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

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


class BacktestPendingOrderBook:
    """
    Maintains pending LIMIT and STOP orders during a backtest.

    Responsibilities:
    - register pending orders
    - cancel pending orders
    - expire pending orders
    - evaluate pending orders against each new candle
    - retain filled/cancelled/expired history

    It does not:
    - update portfolio balances
    - create positions
    - perform risk checks
    - execute live broker orders
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
        metadata: dict | None = None,
    ) -> PendingBacktestOrder:
        """
        Register a LIMIT or STOP order for future execution.
        """

        if order.order_type == OrderType.MARKET:
            raise ValueError("MARKET orders must be executed immediately.")

        resolved_id = order_id or uuid4()

        if resolved_id in self._orders:
            raise ValueError(f"Pending order '{resolved_id}' already exists.")

        pending = PendingBacktestOrder(
            order_id=resolved_id,
            order=order,
            created_at=created_at,
            expiration=expiration,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            metadata=metadata or {},
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
        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise KeyError(f"Pending order '{order_id}' was not found.") from exc

    def all(self) -> list[PendingBacktestOrder]:
        return list(self._orders.values())

    def pending(self) -> list[PendingBacktestOrder]:
        return [order for order in self._orders.values() if order.is_pending]

    def completed(self) -> list[PendingBacktestOrder]:
        return [order for order in self._orders.values() if not order.is_pending]

    def for_symbol(
        self,
        symbol: str,
    ) -> list[PendingBacktestOrder]:
        normalized = self._normalize_symbol(symbol)

        return [
            order
            for order in self.pending()
            if order.order.symbol.upper() == normalized
        ]

    # ------------------------------------------------------------------
    # PROCESSING
    # ------------------------------------------------------------------

    def process_market(
        self,
        market: BacktestMarket,
    ) -> list[PendingBacktestOrder]:
        """
        Evaluate pending orders against the supplied candle.

        Orders are processed in creation order to keep backtests
        deterministic when multiple pending orders trigger on the
        same candle.
        """

        triggered: list[PendingBacktestOrder] = []

        current_time = self._normalize_datetime(market.candle.timestamp)

        # Expire orders first.
        self.expire(current_time)

        candidates = self.for_symbol(market.candle.symbol)

        candidates.sort(key=lambda item: item.created_at)

        for pending in candidates:
            if not pending.is_pending:
                continue

            # Never allow an order to execute before it was created.
            if current_time < pending.created_at:
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
        pending = self.get(order_id)

        if not pending.is_pending:
            raise ValueError(f"Order '{order_id}' is not pending.")

        pending.status = PendingOrderStatus.CANCELLED
        pending.cancelled_at = self._normalize_datetime(
            timestamp or datetime.now(timezone.utc)
        )

        return pending

    def cancel_symbol(
        self,
        symbol: str,
        *,
        timestamp: datetime | None = None,
    ) -> list[PendingBacktestOrder]:
        normalized = self._normalize_symbol(symbol)

        cancelled: list[PendingBacktestOrder] = []

        for pending in self.pending():
            if pending.order.symbol.upper() != normalized:
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
        Expire all orders whose explicit expiration time has passed.
        """

        timestamp = self._normalize_datetime(timestamp)

        expired: list[PendingBacktestOrder] = []

        for pending in self.pending():
            if pending.expiration is None:
                continue

            if timestamp < pending.expiration:
                continue

            pending.status = PendingOrderStatus.EXPIRED
            pending.cancelled_at = timestamp

            expired.append(pending)

        return expired

    # ------------------------------------------------------------------
    # MAINTENANCE
    # ------------------------------------------------------------------

    def remove_completed(self) -> int:
        """
        Remove completed orders from the active book.

        This should only be called if the caller has another mechanism
        for retaining order history.
        """

        completed_ids = [order.order_id for order in self.completed()]

        for order_id in completed_ids:
            del self._orders[order_id]

        return len(completed_ids)

    def clear(self) -> None:
        self._orders.clear()

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def snapshot(self) -> list[dict]:
        """
        Return a serializable representation of the order book.
        """

        return [self._serialize_order(order) for order in self.all()]

    @staticmethod
    def _serialize_order(
        pending: PendingBacktestOrder,
    ) -> dict:
        order = pending.order

        return {
            "order_id": str(pending.order_id),
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "volume": order.volume,
            "price": order.price,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "status": pending.status.value,
            "created_at": pending.created_at,
            "filled_at": pending.filled_at,
            "cancelled_at": pending.cancelled_at,
            "expiration": pending.expiration,
            "strategy_id": pending.strategy_id,
            "strategy_name": pending.strategy_name,
            "fill_id": (
                str(pending.fill.fill_id) if pending.fill is not None else None
            ),
        }

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        if not normalized:
            raise ValueError("Symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
