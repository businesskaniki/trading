"""Broker-neutral execution of approved AQE risk decisions."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.broker.broker_manager import BrokerManager
from app.core.constants import (
    OrderSide as PersistedOrderSide,
    OrderStatus,
    OrderType as PersistedOrderType,
)
from app.database.models.order import Order
from app.database.models.symbol import Symbol
from app.events import EventBus, event_bus
from app.repositories.order_repository import OrderRepository
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide as ExecutionOrderSide,
    OrderType as ExecutionOrderType,
)
from risk.models import RiskDecision

from .account_symbol_resolver import (
    AccountSymbolResolutionError,
    AccountSymbolResolver,
)
from .events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionSubmittedEvent,
)
from .exceptions import ExecutionBrokerError, ExecutionRejectedError
from .mapper import RiskDecisionMapper

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


class ExecutionEngine:
    """Execute approved RiskDecision objects through BrokerManager.

    An AQE order is persisted before the broker boundary is crossed.

    A CREATED order may be reused only when a previous attempt is known
    not to have crossed the broker boundary. SUBMITTED orders are never
    automatically resubmitted by this engine.

    Broker outcomes are mapped conservatively:
        SUCCESS          -> confirmed complete fill, if evidence is complete
        PLACED           -> pending or unresolved submission
        PARTIALLY_FILLED -> confirmed partial fill, if evidence is complete
        UNKNOWN          -> SUBMITTED for reconciliation
        NOT_SUBMITTED    -> CREATED when the no-submission outcome is clear
        REJECTED         -> REJECTED
        FAILED           -> SUBMITTED because the outcome may be ambiguous

    No database session is held open across a broker/network call.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        broker_manager: BrokerManager,
        bus: EventBus | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._broker_manager = broker_manager
        self._bus = bus or event_bus

    async def execute(self, decision: RiskDecision) -> ExecutionResult:
        """Execute one approved decision without blindly resubmitting it."""
        self._validate_decision(decision)
        execution_order = RiskDecisionMapper.to_execution_order(decision)

        try:
            execution_order = await self._resolve_broker_symbol(
                execution_order=execution_order,
            )
        except Exception as exc:
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=False,
            )
            raise

        order = await self._create_order(
            decision=decision,
            execution_order=execution_order,
        )

        try:
            order = await self._mark_order_submitted(
                execution_correlation_id=order.execution_correlation_id,
            )
        except Exception as exc:
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=False,
                order=order,
                metadata={"order_submission_state_update_failed": True},
            )
            raise ExecutionBrokerError(
                "AQE Order could not be marked SUBMITTED before broker "
                "execution. "
                f"execution_correlation_id="
                f"{order.execution_correlation_id!s}."
            ) from exc

        await self._publish(
            ExecutionSubmittedEvent.from_decision(
                decision,
                symbol=execution_order.symbol,
                metadata={
                    "canonical_symbol": decision.symbol,
                    "execution_correlation_id": str(order.execution_correlation_id),
                    "order_id": str(order.id),
                    "order_status": order.status.value,
                },
            )
        )

        # Once place_order begins, a transport exception cannot prove that
        # the broker did not accept the request. Keep the order SUBMITTED.
        try:
            result = await self._broker_manager.place_order(execution_order)
        except Exception as exc:
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=order,
                metadata={"broker_execution_outcome": "unknown"},
            )
            raise ExecutionBrokerError(
                "Broker execution failed or returned no confirmed result. "
                f"symbol={execution_order.symbol!r}, "
                f"account_id={execution_order.account_id!s}, "
                f"execution_correlation_id="
                f"{order.execution_correlation_id!s}. "
                "The order remains SUBMITTED for reconciliation."
            ) from exc

        try:
            persisted_order = await self._update_order_from_result(
                execution_correlation_id=order.execution_correlation_id,
                execution_order=execution_order,
                result=result,
            )
        except Exception as exc:
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=order,
                metadata={
                    "broker_execution_status": self._status_value(result.status),
                    "broker_result_processing_failed": True,
                    "order_reconciliation_failed": True,
                },
            )
            raise ExecutionBrokerError(
                "Broker returned a result but AQE could not persist it "
                "safely. "
                f"execution_correlation_id="
                f"{order.execution_correlation_id!s}."
            ) from exc

        is_pending_order = execution_order.order_type in {
            ExecutionOrderType.LIMIT,
            ExecutionOrderType.STOP,
        }

        # --------------------------------------------------------------
        # CONFIRMED COMPLETE FILL
        # --------------------------------------------------------------
        if result.status is ExecutionStatus.SUCCESS:
            if persisted_order.status is not OrderStatus.FILLED:
                exc = ExecutionBrokerError(
                    "Broker reported SUCCESS, but the available evidence "
                    "does not establish a complete fill. "
                    f"execution_correlation_id="
                    f"{persisted_order.execution_correlation_id!s}. "
                    "The order remains available for reconciliation."
                )
                await self._publish_failed(
                    decision=decision,
                    exc=exc,
                    symbol=execution_order.symbol,
                    execution_submitted=True,
                    order=persisted_order,
                    metadata={
                        "broker_execution_outcome": "inconsistent_or_incomplete",
                        "broker_execution_status": result.status.value,
                        "requires_reconciliation": True,
                    },
                )
                raise exc

            await self._publish(
                ExecutionCompletedEvent.from_result(
                    decision,
                    result,
                    symbol=execution_order.symbol,
                    metadata={
                        "canonical_symbol": decision.symbol,
                        "execution_correlation_id": str(
                            persisted_order.execution_correlation_id
                        ),
                        "order_id": str(persisted_order.id),
                        "order_status": persisted_order.status.value,
                    },
                )
            )
            return result

        # --------------------------------------------------------------
        # ACCEPTED PENDING ORDER OR UNRESOLVED SUBMISSION
        # --------------------------------------------------------------
        if result.status is ExecutionStatus.PLACED:
            if (
                is_pending_order
                and persisted_order.status is OrderStatus.PENDING
                and result.broker_order_id is not None
            ):
                # Successfully placed; this is not a completed execution.
                return result

            if (
                not is_pending_order
                and persisted_order.status is OrderStatus.SUBMITTED
                and result.broker_order_id is not None
            ):
                # The broker acknowledges an order but has not confirmed
                # the market fill. Reconciliation remains necessary.
                return result

            exc = ExecutionBrokerError(
                "Broker reported PLACED without sufficient evidence to "
                "identify and track the broker-side order. "
                f"execution_correlation_id="
                f"{persisted_order.execution_correlation_id!s}."
            )
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=persisted_order,
                metadata={"requires_reconciliation": True},
            )
            raise exc

        # --------------------------------------------------------------
        # CONFIRMED PARTIAL FILL
        # --------------------------------------------------------------
        if result.status is ExecutionStatus.PARTIALLY_FILLED:
            if persisted_order.status is OrderStatus.PARTIALLY_FILLED:
                # A partial fill is a valid broker result, but is not a
                # complete fill and must not emit ExecutionCompletedEvent.
                return result

            exc = ExecutionBrokerError(
                "Broker reported PARTIALLY_FILLED without sufficient "
                "evidence to persist the confirmed partial execution. "
                f"execution_correlation_id="
                f"{persisted_order.execution_correlation_id!s}."
            )
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=persisted_order,
                metadata={"requires_reconciliation": True},
            )
            raise exc

        # --------------------------------------------------------------
        # DEFINITELY NOT SUBMITTED
        # --------------------------------------------------------------
        if result.status is ExecutionStatus.NOT_SUBMITTED:
            if persisted_order.status is OrderStatus.CREATED:
                # The broker explicitly confirms that the submission
                # boundary was not crossed. A later attempt with this same
                # decision ID may safely reuse the CREATED order.
                exc = ExecutionBrokerError(
                    "Broker confirmed that the request was not submitted. "
                    "The AQE order remains CREATED and may be retried "
                    "using the same execution decision. "
                    f"execution_correlation_id="
                    f"{persisted_order.execution_correlation_id!s}."
                )
                await self._publish_failed(
                    decision=decision,
                    exc=exc,
                    symbol=execution_order.symbol,
                    execution_submitted=False,
                    order=persisted_order,
                    metadata={
                        "broker_execution_outcome": "not_submitted",
                        "safe_to_retry": True,
                    },
                )
                raise exc

            # A NOT_SUBMITTED result that conflicts with already observed
            # broker evidence must not reset the order to CREATED.
            exc = ExecutionBrokerError(
                "Broker reported NOT_SUBMITTED, but the persisted order "
                "contains conflicting execution evidence. Reconciliation "
                "is required before retrying. "
                f"execution_correlation_id="
                f"{persisted_order.execution_correlation_id!s}."
            )
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=persisted_order,
                metadata={"requires_reconciliation": True},
            )
            raise exc

        # --------------------------------------------------------------
        # EXPLICIT BROKER REJECTION
        # --------------------------------------------------------------
        if result.status is ExecutionStatus.REJECTED:
            rejection_exception = ExecutionRejectedError(
                result.message
                or f"Broker rejected execution for {execution_order.symbol!r}."
            )
            await self._publish_failed(
                decision=decision,
                exc=rejection_exception,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=persisted_order,
                metadata={
                    "broker_execution_outcome": "rejected",
                    "broker_execution_status": result.status.value,
                    "broker_order_id": _string_or_none(result.broker_order_id),
                    "broker_deal_id": _string_or_none(result.broker_deal_id),
                    "broker_position_id": _string_or_none(result.broker_position_id),
                },
            )
            raise rejection_exception

        # --------------------------------------------------------------
        # UNKNOWN OR LEGACY FAILED RESULT
        # --------------------------------------------------------------
        if result.status in {
            ExecutionStatus.UNKNOWN,
            ExecutionStatus.FAILED,
        }:
            exc = ExecutionBrokerError(
                result.message
                or (
                    "Broker outcome is not confirmed. "
                    f"status={result.status.value}, "
                    f"symbol={execution_order.symbol!r}."
                )
            )
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=persisted_order,
                metadata={
                    "broker_execution_outcome": "unknown",
                    "broker_execution_status": result.status.value,
                    "requires_reconciliation": True,
                },
            )
            raise exc

        # Defensive guard for future additions to ExecutionStatus.
        raise ExecutionBrokerError(
            "Unsupported broker execution result status: " f"{result.status!r}."
        )

    async def _create_order(
        self,
        *,
        decision: RiskDecision,
        execution_order: ExecutionOrder,
    ) -> Order:
        """Create an order, or reuse a matching CREATED order for safe retry."""
        async with self._session_factory() as db:
            orders = OrderRepository(db)

            symbol_id = await self._resolve_canonical_symbol_id(
                db=db,
                symbol=decision.symbol,
            )
            account_id = self._require_account_id(
                execution_order.account_id,
            )

            existing_order = await orders.get_by_execution_correlation_id(
                decision.decision_id,
            )
            if existing_order is not None:
                self._validate_existing_order_matches(
                    existing_order,
                    decision=decision,
                    execution_order=execution_order,
                    account_id=account_id,
                    symbol_id=symbol_id,
                )

                if existing_order.status is OrderStatus.CREATED:
                    # CREATED means the broker boundary was not crossed.
                    return existing_order

                raise ExecutionRejectedError(
                    "An AQE Order already exists for execution decision "
                    f"{decision.decision_id!s} with status "
                    f"{existing_order.status.value!r}. "
                    "The same decision cannot be submitted again."
                )

            order = Order(
                execution_correlation_id=decision.decision_id,
                strategy=decision.strategy_name,
                comment=execution_order.comment,
                account_id=account_id,
                symbol_id=symbol_id,
                broker_symbol=execution_order.symbol,
                order_type=self._map_order_type(execution_order.order_type),
                side=self._map_order_side(execution_order.side),
                volume=execution_order.volume,
                executed_volume=None,
                requested_price=execution_order.price,
                executed_price=None,
                stop_loss=execution_order.stop_loss,
                take_profit=execution_order.take_profit,
                status=OrderStatus.CREATED,
            )

            try:
                return await orders.create(order)
            except IntegrityError as exc:
                await db.rollback()

                existing_order = await orders.get_by_execution_correlation_id(
                    decision.decision_id,
                )
                if existing_order is not None:
                    self._validate_existing_order_matches(
                        existing_order,
                        decision=decision,
                        execution_order=execution_order,
                        account_id=account_id,
                        symbol_id=symbol_id,
                    )

                    if existing_order.status is OrderStatus.CREATED:
                        return existing_order

                    raise ExecutionRejectedError(
                        "Execution decision was already persisted as "
                        f"AQE Order {existing_order.id!s}. "
                        "It cannot be resubmitted from its current state."
                    ) from exc

                raise ExecutionBrokerError(
                    "Failed to persist AQE Order before broker submission. "
                    f"execution_correlation_id={decision.decision_id!s}."
                ) from exc

    @staticmethod
    def _validate_existing_order_matches(
        order: Order,
        *,
        decision: RiskDecision,
        execution_order: ExecutionOrder,
        account_id: UUID,
        symbol_id: UUID,
    ) -> None:
        """Prevent a reused correlation ID from changing the original intent."""
        expected = {
            "account_id": account_id,
            "symbol_id": symbol_id,
            "broker_symbol": execution_order.symbol,
            "order_type": ExecutionEngine._map_order_type(execution_order.order_type),
            "side": ExecutionEngine._map_order_side(execution_order.side),
            "volume": execution_order.volume,
            "requested_price": execution_order.price,
            "stop_loss": execution_order.stop_loss,
            "take_profit": execution_order.take_profit,
            "strategy": decision.strategy_name,
        }

        for field, value in expected.items():
            if getattr(order, field) != value:
                raise ExecutionRejectedError(
                    "Existing AQE Order does not match the supplied "
                    f"execution decision: field={field!r}, "
                    f"execution_correlation_id="
                    f"{decision.decision_id!s}."
                )

    async def _mark_order_submitted(
        self,
        *,
        execution_correlation_id: UUID,
    ) -> Order:
        """Persist SUBMITTED immediately before crossing the broker boundary."""
        async with self._session_factory() as db:
            orders = OrderRepository(db)
            order = await orders.get_by_execution_correlation_id(
                execution_correlation_id,
            )
            if order is None:
                raise ExecutionBrokerError(
                    "AQE Order not found while marking it SUBMITTED. "
                    f"execution_correlation_id={execution_correlation_id!s}."
                )

            if order.status is not OrderStatus.CREATED:
                raise ExecutionRejectedError(
                    "AQE Order cannot transition to SUBMITTED from "
                    f"{order.status.value!r}. "
                    f"execution_correlation_id={execution_correlation_id!s}."
                )

            order.status = OrderStatus.SUBMITTED
            db.add(order)
            await db.commit()
            await db.refresh(order)
            return order

    async def _update_order_from_result(
        self,
        *,
        execution_correlation_id: UUID,
        execution_order: ExecutionOrder,
        result: ExecutionResult,
    ) -> Order:
        """Persist broker identifiers and only confirmed execution evidence.

        An order ID proves that a broker-side order exists; by itself, it does
        not prove that a deal filled. A fill therefore requires a broker deal
        ID plus finite, positive executed volume and execution price. The
        confirmed volume must not exceed the requested volume.
        """
        requested_volume = _as_finite_decimal(execution_order.volume)
        actual_volume = _as_finite_decimal(result.volume)
        actual_price = _as_finite_decimal(result.price)

        if requested_volume is None or requested_volume <= Decimal("0"):
            raise ExecutionBrokerError(
                "Cannot persist execution because requested volume is invalid. "
                f"execution_correlation_id={execution_correlation_id!s}."
            )

        async with self._session_factory() as db:
            orders = OrderRepository(db)
            order = await orders.get_by_execution_correlation_id(
                execution_correlation_id,
            )
            if order is None:
                raise ExecutionBrokerError(
                    "AQE Order not found while reconciling broker execution. "
                    f"execution_correlation_id={execution_correlation_id!s}."
                )

            # Preserve known identifiers when a later result omits them.
            if _identifier_present(result.broker_order_id):
                order.broker_order_id = result.broker_order_id
            if _identifier_present(result.broker_deal_id):
                order.broker_deal_id = result.broker_deal_id
            if _identifier_present(result.broker_position_id):
                order.broker_position_id = result.broker_position_id

            has_broker_identity = any(
                _identifier_present(value)
                for value in (
                    order.broker_order_id,
                    order.broker_deal_id,
                    order.broker_position_id,
                )
            )
            has_execution_evidence = (
                has_broker_identity
                or order.executed_volume is not None
                or order.executed_price is not None
            )

            valid_volume = (
                actual_volume is not None
                and actual_volume > Decimal("0")
                and actual_volume <= requested_volume
            )
            valid_price = actual_price is not None and actual_price > Decimal("0")
            has_confirmed_fill_evidence = (
                _identifier_present(order.broker_deal_id)
                and valid_volume
                and valid_price
            )

            if result.status is ExecutionStatus.SUCCESS:
                if has_confirmed_fill_evidence:
                    # Persist only broker-confirmed executed values.
                    order.executed_volume = actual_volume
                    order.executed_price = actual_price

                    if actual_volume == requested_volume:
                        order.status = OrderStatus.FILLED
                    else:
                        # The broker said SUCCESS, but the confirmed quantity
                        # is smaller than requested. Record the actual partial
                        # fill rather than falsely declaring a full fill.
                        order.status = OrderStatus.PARTIALLY_FILLED
                else:
                    order.status = OrderStatus.SUBMITTED

            elif result.status is ExecutionStatus.PARTIALLY_FILLED:
                if has_confirmed_fill_evidence and actual_volume < requested_volume:
                    order.executed_volume = actual_volume
                    order.executed_price = actual_price
                    order.status = OrderStatus.PARTIALLY_FILLED
                else:
                    # Incomplete or contradictory evidence is unresolved.
                    # Do not persist a claimed fill quantity as confirmed.
                    order.status = OrderStatus.SUBMITTED

            elif result.status is ExecutionStatus.PLACED:
                is_pending_order = execution_order.order_type in {
                    ExecutionOrderType.LIMIT,
                    ExecutionOrderType.STOP,
                }

                if is_pending_order and _identifier_present(order.broker_order_id):
                    order.status = OrderStatus.PENDING
                else:
                    # PLACED is not proof of a market-order fill.
                    order.status = OrderStatus.SUBMITTED

            elif result.status is ExecutionStatus.NOT_SUBMITTED:
                if not has_execution_evidence:
                    # The broker confirms that no submission occurred.
                    # CREATED permits a later safe retry with this ID.
                    order.status = OrderStatus.CREATED
                else:
                    # Conflicting evidence must not enable resubmission.
                    order.status = OrderStatus.SUBMITTED

            elif result.status is ExecutionStatus.REJECTED:
                order.status = OrderStatus.REJECTED

            elif result.status in {
                ExecutionStatus.UNKNOWN,
                ExecutionStatus.FAILED,
            }:
                order.status = OrderStatus.SUBMITTED

            else:
                raise ExecutionBrokerError(
                    "Unsupported ExecutionResult status during persistence: "
                    f"{result.status!r}."
                )

            db.add(order)
            await db.commit()
            await db.refresh(order)
            return order

    async def _resolve_canonical_symbol_id(
        self,
        *,
        db: AsyncSession,
        symbol: str,
    ) -> UUID:
        """Resolve the canonical AQE Symbol UUID used by Order.symbol_id."""
        canonical_symbol = str(symbol).strip().upper()
        if not canonical_symbol:
            raise ExecutionRejectedError(
                "Cannot persist an order without a canonical symbol."
            )

        result = await db.execute(
            select(Symbol.id).where(Symbol.name == canonical_symbol),
        )
        symbol_id = result.scalar_one_or_none()
        if symbol_id is None:
            raise ExecutionBrokerError(
                "Canonical AQE symbol was not found for execution: "
                f"{canonical_symbol!r}."
            )
        return symbol_id

    async def _resolve_broker_symbol(
        self,
        *,
        execution_order: ExecutionOrder,
    ) -> ExecutionOrder:
        """Resolve a canonical AQE symbol to the selected account's symbol."""
        account_id = self._require_account_id(execution_order.account_id)

        async with self._session_factory() as db:
            resolver = AccountSymbolResolver(db)
            try:
                broker_symbol = await resolver.resolve(
                    account_id=account_id,
                    symbol=execution_order.symbol,
                )
            except AccountSymbolResolutionError as exc:
                raise ExecutionBrokerError(
                    "Unable to resolve broker symbol for execution: "
                    f"account_id={account_id}, "
                    f"symbol={execution_order.symbol!r}."
                ) from exc
            except Exception as exc:
                raise ExecutionBrokerError(
                    "Unexpected failure while resolving broker symbol: "
                    f"account_id={account_id}, "
                    f"symbol={execution_order.symbol!r}."
                ) from exc

        return execution_order.model_copy(update={"symbol": broker_symbol})

    async def _publish(self, event: object) -> None:
        """Publish lifecycle events without triggering broker retries."""
        try:
            await self._bus.publish(event)
        except Exception:
            logger.exception(
                "Execution event publication failed: event_type=%s",
                type(event).__name__,
            )

    async def _publish_failed(
        self,
        *,
        decision: RiskDecision,
        exc: Exception,
        symbol: str,
        execution_submitted: bool,
        order: Order | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Publish failure details without masking the original exception."""
        event_metadata = {
            "canonical_symbol": decision.symbol,
            "execution_submitted": execution_submitted,
        }

        if order is not None:
            event_metadata.update(
                {
                    "execution_correlation_id": str(order.execution_correlation_id),
                    "order_id": str(order.id),
                    "order_status": order.status.value,
                }
            )

        if metadata:
            event_metadata.update(metadata)

        try:
            event = ExecutionFailedEvent.from_exception(
                decision,
                exc,
                symbol=symbol,
                metadata=event_metadata,
            )
            await self._publish(event)
        except Exception:
            logger.exception(
                "Failed to publish execution failure: decision_id=%s",
                decision.decision_id,
            )

    @staticmethod
    def _validate_decision(decision: RiskDecision) -> None:
        """Validate the minimum contract required by execution."""
        if not decision.approved:
            raise ExecutionRejectedError(
                "Execution requires an approved RiskDecision. "
                f"Decision status: {decision.status.value}"
            )
        if decision.account_id is None:
            raise ExecutionRejectedError(
                "Execution requires a RiskDecision with an account_id."
            )
        if not str(decision.symbol).strip():
            raise ExecutionRejectedError(
                "Execution requires a RiskDecision with a symbol."
            )
        if decision.position_size is None:
            raise ExecutionRejectedError(
                "Execution requires a RiskDecision with a position_size."
            )
        if decision.position_size <= Decimal("0"):
            raise ExecutionRejectedError(
                "Execution requires a positive RiskDecision position_size."
            )

    @staticmethod
    def _map_order_side(side: ExecutionOrderSide) -> PersistedOrderSide:
        """Map execution-side values to the persisted AQE enum."""
        if side is ExecutionOrderSide.BUY:
            return PersistedOrderSide.BUY
        if side is ExecutionOrderSide.SELL:
            return PersistedOrderSide.SELL
        raise ExecutionRejectedError(f"Unsupported execution order side: {side!r}.")

    @staticmethod
    def _map_order_type(
        order_type: ExecutionOrderType,
    ) -> PersistedOrderType:
        """Map execution order types to the persisted AQE enum."""
        if order_type is ExecutionOrderType.MARKET:
            return PersistedOrderType.MARKET
        if order_type is ExecutionOrderType.LIMIT:
            return PersistedOrderType.LIMIT
        if order_type is ExecutionOrderType.STOP:
            return PersistedOrderType.STOP
        raise ExecutionRejectedError(
            f"Unsupported execution order type: {order_type!r}."
        )

    @staticmethod
    def _require_account_id(account_id: UUID | str | None) -> UUID:
        """Normalize an execution account ID to UUID."""
        if account_id is None:
            raise ExecutionRejectedError("Execution requires an account_id.")
        if isinstance(account_id, UUID):
            return account_id

        try:
            return UUID(str(account_id))
        except (TypeError, ValueError) as exc:
            raise ExecutionRejectedError(
                f"Invalid execution account_id: {account_id!r}."
            ) from exc

    @staticmethod
    def _status_value(status: object) -> str:
        """Return a log-safe representation of a broker status."""
        return str(getattr(status, "value", status))


def _as_finite_decimal(value: object) -> Decimal | None:
    """Convert a value to a finite Decimal, returning None if invalid."""
    if value is None:
        return None

    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if not normalized.is_finite():
        return None
    return normalized


def _identifier_present(value: object) -> bool:
    """Return whether an optional broker identifier contains a value."""
    return value is not None and bool(str(value).strip())


def _string_or_none(value: object) -> str | None:
    """Convert an optional broker identifier to a serialization-safe string."""
    if value is None:
        return None
    return str(value)
