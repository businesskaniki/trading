from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.schemas.execution import ExecutionResult
from risk.models import RiskDecision


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ExecutionSubmittedEvent:
    """
    Published immediately before an approved execution order is submitted
    to the broker.

    `decision_id` is the AQE execution correlation identifier.

    `symbol` is the broker-facing symbol after account-specific symbol
    resolution. The original canonical AQE symbol is preserved in metadata.
    """

    decision_id: UUID
    signal_id: UUID
    account_id: UUID

    strategy_id: str
    strategy_name: str

    symbol: str
    direction: str
    order_type: str

    position_size: Decimal

    entry_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None

    occurred_at: datetime = field(default_factory=_utc_now)
    event_id: UUID = field(default_factory=uuid4)

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_decision(
        cls,
        decision: RiskDecision,
        *,
        symbol: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionSubmittedEvent:
        return cls(
            decision_id=decision.decision_id,
            signal_id=decision.signal_id,
            account_id=decision.account_id,
            strategy_id=decision.strategy_id,
            strategy_name=decision.strategy_name,
            symbol=symbol or decision.symbol,
            direction=decision.direction.value,
            order_type=decision.order_type.value,
            position_size=decision.position_size,
            entry_price=decision.entry_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            metadata=dict(metadata or {}),
        )

    @property
    def event_type(self) -> str:
        return "execution.submitted"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "decision_id": str(self.decision_id),
            "signal_id": str(self.signal_id),
            "account_id": str(self.account_id),
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "direction": self.direction,
            "order_type": self.order_type,
            "position_size": str(self.position_size),
            "entry_price": _decimal_string(self.entry_price),
            "stop_loss": _decimal_string(self.stop_loss),
            "take_profit": _decimal_string(self.take_profit),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExecutionCompletedEvent:
    """
    Published after the broker successfully processes the execution.

    `decision_id` is the primary AQE correlation key.

    Broker identifiers are retained separately because they represent
    broker-side objects and must never be confused with AQE identifiers.
    """

    decision_id: UUID
    signal_id: UUID
    account_id: UUID

    strategy_id: str
    strategy_name: str

    symbol: str
    status: str

    broker_order_id: str | None
    broker_deal_id: str | None
    broker_position_id: str | None

    volume: Decimal | None
    price: Decimal | None

    message: str | None

    occurred_at: datetime = field(default_factory=_utc_now)
    event_id: UUID = field(default_factory=uuid4)

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(
        cls,
        decision: RiskDecision,
        result: ExecutionResult,
        *,
        symbol: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionCompletedEvent:
        return cls(
            decision_id=decision.decision_id,
            signal_id=decision.signal_id,
            account_id=decision.account_id,
            strategy_id=decision.strategy_id,
            strategy_name=decision.strategy_name,
            symbol=symbol or decision.symbol,
            status=result.status.value,
            broker_order_id=_string_or_none(
                getattr(result, "broker_order_id", None)
            ),
            broker_deal_id=_string_or_none(
                getattr(result, "broker_deal_id", None)
            ),
            broker_position_id=_string_or_none(
                getattr(result, "broker_position_id", None)
            ),
            volume=_decimal_or_none(
                getattr(result, "volume", None)
            ),
            price=_decimal_or_none(
                getattr(result, "price", None)
            ),
            message=_string_or_none(
                getattr(result, "message", None)
            ),
            metadata=dict(metadata or {}),
        )

    @property
    def event_type(self) -> str:
        return "execution.completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "decision_id": str(self.decision_id),
            "signal_id": str(self.signal_id),
            "account_id": str(self.account_id),
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "status": self.status,
            "broker_order_id": self.broker_order_id,
            "broker_deal_id": self.broker_deal_id,
            "broker_position_id": self.broker_position_id,
            "volume": _decimal_string(self.volume),
            "price": _decimal_string(self.price),
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExecutionFailedEvent:
    """
    Published when an approved execution cannot be completed.

    `decision_id` remains the correlation identifier even though no
    successful broker execution exists.
    """

    decision_id: UUID
    signal_id: UUID
    account_id: UUID

    strategy_id: str
    strategy_name: str

    symbol: str

    error_type: str
    error_message: str

    occurred_at: datetime = field(default_factory=_utc_now)
    event_id: UUID = field(default_factory=uuid4)

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(
        cls,
        decision: RiskDecision,
        exc: Exception,
        *,
        symbol: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionFailedEvent:
        return cls(
            decision_id=decision.decision_id,
            signal_id=decision.signal_id,
            account_id=decision.account_id,
            strategy_id=decision.strategy_id,
            strategy_name=decision.strategy_name,
            symbol=symbol or decision.symbol,
            error_type=type(exc).__name__,
            error_message=str(exc),
            metadata=dict(metadata or {}),
        )

    @property
    def event_type(self) -> str:
        return "execution.failed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "decision_id": str(self.decision_id),
            "signal_id": str(self.signal_id),
            "account_id": str(self.account_id),
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
        }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return str(value)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)


__all__ = [
    "ExecutionSubmittedEvent",
    "ExecutionCompletedEvent",
    "ExecutionFailedEvent",
]