from __future__ import annotations

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
from app.repositories.order_repository import OrderRepository
from app.events import EventBus, event_bus
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


SessionFactory = async_sessionmaker[AsyncSession]


class ExecutionEngine:
    """
    Execute approved RiskDecisions through the configured BrokerManager.

    Execution flow:

        RiskDecision
            ↓
        validation
            ↓
        RiskDecisionMapper
            ↓
        broker-symbol resolution
            ↓
        persist AQE Order
            ↓
        ExecutionSubmittedEvent
            ↓
        BrokerManager.place_order()
            ↓
        ExecutionResult
            ↓
        reconcile persisted AQE Order
            ↓
        ExecutionCompletedEvent
            or
        ExecutionFailedEvent

    Responsibilities:
        - accept only approved RiskDecision objects;
        - convert RiskDecision to ExecutionOrder;
        - resolve canonical AQE symbols to broker symbols;
        - persist an AQE Order before broker submission;
        - use RiskDecision.decision_id as the execution correlation ID;
        - submit through BrokerManager;
        - persist broker execution identifiers;
        - publish execution lifecycle events.

    The execution engine does NOT:
        - calculate risk;
        - generate signals;
        - modify risk parameters;
        - communicate directly with MT5;
        - contain broker-specific execution logic;
        - write broker-specific mapping logic.

    Database sessions are intentionally short-lived and scoped to
    individual persistence operations. A single AsyncSession is never
    held across a broker/network call.
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

    # ======================================================================
    # PUBLIC EXECUTION
    # ======================================================================

    async def execute(
        self,
        decision: RiskDecision,
    ) -> ExecutionResult:
        """
        Execute an approved RiskDecision.

        The AQE Order is persisted before broker submission.

        RiskDecision.decision_id becomes the deterministic
        execution_correlation_id for the entire execution lifecycle.

        The broker is called only after the AQE Order exists.

        After broker execution, a new database session is used to reconcile
        the persisted Order with the broker result.
        """

        self._validate_decision(decision)

        execution_order = RiskDecisionMapper.to_execution_order(decision)

        # ------------------------------------------------------------------
        # 1. Resolve canonical AQE symbol -> broker symbol
        # ------------------------------------------------------------------

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

        # ------------------------------------------------------------------
        # 2. Persist the AQE order BEFORE broker submission
        # ------------------------------------------------------------------

        order = await self._create_order(
            decision=decision,
            execution_order=execution_order,
        )

        # ------------------------------------------------------------------
        # 3. Publish submission event
        # ------------------------------------------------------------------

        submitted_event = ExecutionSubmittedEvent.from_decision(
            decision,
            symbol=execution_order.symbol,
            metadata={
                "canonical_symbol": decision.symbol,
                "execution_correlation_id": str(
                    order.execution_correlation_id
                ),
                "order_id": str(order.id),
            },
        )

        await self._publish(submitted_event)

        # ------------------------------------------------------------------
        # 4. Submit to broker
        # ------------------------------------------------------------------

        try:
            result = await self._broker_manager.place_order(
                execution_order
            )
        except Exception as exc:
            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=order,
            )

            raise ExecutionBrokerError(
                "Broker execution failed for "
                f"symbol={execution_order.symbol!r}, "
                f"account_id={execution_order.account_id!s}, "
                f"execution_correlation_id="
                f"{order.execution_correlation_id!s}."
            ) from exc

        # ------------------------------------------------------------------
        # 5. Reconcile broker result into AQE persistence
        # ------------------------------------------------------------------

        try:
            persisted_order = await self._update_order_from_result(
                execution_correlation_id=order.execution_correlation_id,
                execution_order=execution_order,
                result=result,
            )
        except Exception as exc:
            """
            The broker has already accepted/responded to the order.

            NEVER submit the same RiskDecision again merely because AQE
            persistence failed after broker execution.

            Reconciliation is responsible for recovering the persisted
            state.
            """

            await self._publish_failed(
                decision=decision,
                exc=exc,
                symbol=execution_order.symbol,
                execution_submitted=True,
                order=order,
                metadata={
                    "broker_execution_succeeded": True,
                    "order_persistence_failed": True,
                },
            )

            raise ExecutionBrokerError(
                "Broker execution succeeded but AQE could not reconcile "
                "the execution result. "
                f"execution_correlation_id="
                f"{order.execution_correlation_id!s}."
            ) from exc

        # ------------------------------------------------------------------
        # 6. Publish completed event
        # ------------------------------------------------------------------

        completed_event = ExecutionCompletedEvent.from_result(
            decision,
            result,
            symbol=execution_order.symbol,
            metadata={
                "canonical_symbol": decision.symbol,
                "execution_correlation_id": str(
                    persisted_order.execution_correlation_id
                ),
                "order_id": str(persisted_order.id),
            },
        )

        await self._publish(completed_event)

        return result

    # ======================================================================
    # ORDER PERSISTENCE
    # ======================================================================

    async def _create_order(
        self,
        *,
        decision: RiskDecision,
        execution_order: ExecutionOrder,
    ) -> Order:
        """
        Create the AQE Order before broker submission.

        A dedicated database session is used only for this transaction.

        RiskDecision.decision_id is the deterministic execution
        correlation identifier.
        """

        async with self._session_factory() as db:
            orders = OrderRepository(db)

            existing_order = (
                await orders.get_by_execution_correlation_id(
                    decision.decision_id
                )
            )

            if existing_order is not None:
                raise ExecutionRejectedError(
                    "An AQE Order already exists for execution decision "
                    f"{decision.decision_id!s}. "
                    "The same RiskDecision cannot be submitted twice."
                )

            symbol_id = await self._resolve_canonical_symbol_id(
                db=db,
                symbol=decision.symbol,
            )

            order = Order(
                execution_correlation_id=decision.decision_id,
                strategy=decision.strategy_name,
                comment=execution_order.comment,
                account_id=self._require_account_id(
                    execution_order.account_id
                ),
                symbol_id=symbol_id,
                order_type=self._map_order_type(
                    execution_order.order_type
                ),
                side=self._map_order_side(
                    execution_order.side
                ),
                volume=execution_order.volume,
                requested_price=execution_order.price,
                executed_price=None,
                stop_loss=execution_order.stop_loss,
                take_profit=execution_order.take_profit,
                status=OrderStatus.CREATED,
            )

            try:
                created_order = await orders.create(order)
            except IntegrityError as exc:
                await db.rollback()

                existing_order = (
                    await orders.get_by_execution_correlation_id(
                        decision.decision_id
                    )
                )

                if existing_order is not None:
                    raise ExecutionRejectedError(
                        "Execution decision has already been persisted as "
                        f"AQE Order {existing_order.id!s}. "
                        "The same RiskDecision cannot be submitted twice."
                    ) from exc

                raise ExecutionBrokerError(
                    "Failed to persist AQE Order before broker submission "
                    "for execution_correlation_id="
                    f"{decision.decision_id!s}."
                ) from exc

            return created_order

    async def _update_order_from_result(
        self,
        *,
        execution_correlation_id: UUID,
        execution_order: ExecutionOrder,
        result: ExecutionResult,
    ) -> Order:
        """
        Reconcile the broker result into the persisted AQE Order.

        A completely fresh database session is used because the original
        persistence session was intentionally closed before broker
        execution.
        """

        async with self._session_factory() as db:
            orders = OrderRepository(db)

            order = await orders.get_by_execution_correlation_id(
                execution_correlation_id
            )

            if order is None:
                raise ExecutionBrokerError(
                    "AQE Order could not be found while reconciling "
                    "broker execution. "
                    f"execution_correlation_id="
                    f"{execution_correlation_id!s}."
                )

            order.broker_order_id = result.broker_order_id
            order.broker_deal_id = result.broker_deal_id
            order.broker_position_id = result.broker_position_id

            if result.price is not None:
                order.executed_price = result.price

            if result.volume is not None:
                order.volume = result.volume

            if result.status is ExecutionStatus.SUCCESS:
                if execution_order.order_type in {
                    ExecutionOrderType.LIMIT,
                    ExecutionOrderType.STOP,
                }:
                    order.status = OrderStatus.PENDING
                else:
                    order.status = OrderStatus.FILLED

            elif result.status is ExecutionStatus.REJECTED:
                """
                The current AQE OrderStatus enum does not define REJECTED.

                Do not incorrectly represent a broker rejection as
                CANCELLED or FILLED.

                The execution event contains the authoritative broker
                rejection information, while reconciliation can later
                introduce a dedicated failure/rejection state.
                """

                order.status = OrderStatus.CREATED

            elif result.status is ExecutionStatus.FAILED:
                """
                The current AQE OrderStatus enum does not define FAILED.

                Keep the order CREATED so reconciliation can distinguish
                an unconfirmed execution from a cancelled or filled order.
                """

                order.status = OrderStatus.CREATED

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
        """
        Resolve the canonical AQE Symbol UUID.

        Order.symbol_id always stores the canonical AQE symbol.

        Broker symbol resolution is handled separately by
        AccountSymbolResolver.
        """

        canonical_symbol = str(symbol).strip().upper()

        if not canonical_symbol:
            raise ExecutionRejectedError(
                "Cannot persist an order without a canonical symbol."
            )

        result = await db.execute(
            select(Symbol.id).where(
                Symbol.name == canonical_symbol
            )
        )

        symbol_id = result.scalar_one_or_none()

        if symbol_id is None:
            raise ExecutionBrokerError(
                "Canonical AQE symbol was not found for execution: "
                f"{canonical_symbol!r}."
            )

        return symbol_id

    # ======================================================================
    # BROKER SYMBOL RESOLUTION
    # ======================================================================

    async def _resolve_broker_symbol(
        self,
        *,
        execution_order: ExecutionOrder,
    ) -> ExecutionOrder:
        """
        Translate canonical AQE symbol into the account-specific
        broker symbol.

        Example:

            XAUUSD → XAUUSD.s

        The broker-facing symbol exists only inside ExecutionOrder.

        The canonical symbol remains represented by:
            RiskDecision.symbol
            Order.symbol_id
        """

        account_id = self._require_account_id(
            execution_order.account_id
        )

        # AccountSymbolResolver is intentionally created for this
        # operation rather than holding a database session for the
        # lifetime of ExecutionEngine.
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
                    "Unexpected failure while resolving broker symbol "
                    "for "
                    f"account_id={account_id}, "
                    f"symbol={execution_order.symbol!r}."
                ) from exc

        return execution_order.model_copy(
            update={
                "symbol": broker_symbol,
            }
        )

    # ======================================================================
    # EVENT PUBLICATION
    # ======================================================================

    async def _publish(
        self,
        event: object,
    ) -> None:
        """
        Publish an execution lifecycle event.

        Event infrastructure failure must not cause broker execution
        to be retried.

        A successful broker execution must never be duplicated solely
        because event publication failed.
        """

        try:
            await self._bus.publish(event)
        except Exception:
            return

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
        """
        Publish an execution failure event without masking the original
        execution exception.
        """

        event_metadata = {
            "canonical_symbol": decision.symbol,
            "execution_submitted": execution_submitted,
        }

        if order is not None:
            event_metadata.update(
                {
                    "execution_correlation_id": str(
                        order.execution_correlation_id
                    ),
                    "order_id": str(order.id),
                }
            )

        if metadata:
            event_metadata.update(metadata)

        event = ExecutionFailedEvent.from_exception(
            decision,
            exc,
            symbol=symbol,
            metadata=event_metadata,
        )

        await self._publish(event)

    # ======================================================================
    # VALIDATION
    # ======================================================================

    @staticmethod
    def _validate_decision(
        decision: RiskDecision,
    ) -> None:
        """
        Validate the minimum execution contract.

        The Execution Engine assumes Risk Engine validation has already
        occurred. It does not re-run risk calculations.
        """

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

    # ======================================================================
    # ENUM MAPPING
    # ======================================================================

    @staticmethod
    def _map_order_side(
        side: ExecutionOrderSide,
    ) -> PersistedOrderSide:
        """
        Map the execution-layer side enum to the persisted AQE enum.
        """

        if side is ExecutionOrderSide.BUY:
            return PersistedOrderSide.BUY

        if side is ExecutionOrderSide.SELL:
            return PersistedOrderSide.SELL

        raise ExecutionRejectedError(
            f"Unsupported execution order side: {side!r}."
        )

    @staticmethod
    def _map_order_type(
        order_type: ExecutionOrderType,
    ) -> PersistedOrderType:
        """
        Map the execution-layer order type enum to the persisted
        AQE order enum.
        """

        if order_type is ExecutionOrderType.MARKET:
            return PersistedOrderType.MARKET

        if order_type is ExecutionOrderType.LIMIT:
            return PersistedOrderType.LIMIT

        if order_type is ExecutionOrderType.STOP:
            return PersistedOrderType.STOP

        raise ExecutionRejectedError(
            f"Unsupported execution order type: {order_type!r}."
        )

    # ======================================================================
    # ACCOUNT VALIDATION
    # ======================================================================

    @staticmethod
    def _require_account_id(
        account_id: UUID | str | None,
    ) -> UUID:
        """
        Normalize an execution account ID to UUID.
        """

        if account_id is None:
            raise ExecutionRejectedError(
                "Execution requires an account_id."
            )

        if isinstance(account_id, UUID):
            return account_id

        try:
            return UUID(str(account_id))
        except (TypeError, ValueError) as exc:
            raise ExecutionRejectedError(
                f"Invalid execution account_id: {account_id!r}."
            ) from exc