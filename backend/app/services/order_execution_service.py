
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from app.core.constants import OrderStatus
from app.database.models.order import Order
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.order_repository import OrderRepository
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)
from app.services.execution_service import ExecutionService

logger = logging.getLogger(__name__)


class OrderExecutionService:
    """
    Application service orchestrating AQE order submission.

    Responsibilities:
        1. Load and lock a CREATED AQE order.
        2. Validate account ownership and order state.
        3. Resolve and persist the broker-native symbol.
        4. Build a broker-independent ExecutionOrder.
        5. Commit SUBMITTED before crossing the broker boundary.
        6. Interpret broker outcomes without inventing fills.
        7. Persist broker identifiers and confirmed execution data.

    Important invariants:
        - Only CREATED orders can enter normal submission.
        - SUBMITTED is durable before the external broker request.
        - An exception after submission begins does not prove rejection.
        - UNKNOWN remains SUBMITTED for reconciliation.
        - NOT_SUBMITTED can return the order to CREATED.
        - A pending-order acceptance is not a fill.
        - Execution volume and price must be broker-confirmed.
    """

    def __init__(
        self,
        order_repository: OrderRepository,
        execution_service: ExecutionService,
        account_symbol_repository: AccountSymbolRepository,
    ) -> None:
        self.order_repository = order_repository
        self.execution_service = execution_service
        self.account_symbol_repository = account_symbol_repository

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    async def execute_order(
        self,
        order_id: UUID,
        user_id,
    ) -> Order:
        """
        Submit an existing CREATED order.

        The submission state is committed before invoking the broker.
        If the process subsequently fails, reconciliation can find the
        durable SUBMITTED record.
        """

        db = self.order_repository.db

        order = await self.order_repository.get_by_id_for_update(
            order_id,
        )

        if order is None:
            raise ValueError("Order not found.")

        if order.account is None:
            raise ValueError("Order trading account is unavailable.")

        if order.account.user_id != user_id:
            raise PermissionError(
                "You do not have permission to execute this order."
            )

        self._validate_order_state(order)

        broker_symbol = await self._resolve_broker_symbol(
            order,
        )

        execution_order = self._build_execution_order(
            order,
            broker_symbol,
        )

        # Persist the exact instrument sent to the broker.
        order.broker_symbol = broker_symbol

        # This is a recovery marker, not proof that the broker
        # accepted or filled the order.
        order.status = OrderStatus.SUBMITTED

        # CRITICAL: commit before making the external broker call.
        # If this commit fails, execution must not be attempted.
        await db.commit()

        # Refresh the scalar columns after commit before continuing.
        await db.refresh(order)

        logger.info(
            "Submitting AQE order to broker. "
            "order_id=%s account_id=%s symbol=%s side=%s type=%s "
            "volume=%s",
            order.id,
            order.account_id,
            broker_symbol,
            order.side.value,
            order.order_type.value,
            order.volume,
        )

        try:
            result = await self.execution_service.execute_order(
                execution_order,
            )

        except Exception as exc:
            # An exception here does not establish that the broker
            # failed to execute. Keep the durable recovery marker.
            #
            # Broker adapters should return NOT_SUBMITTED for failures
            # they can prove occurred before broker submission.
            logger.exception(
                "Order submission raised an exception. "
                "Keeping order recoverable. order_id=%s",
                order.id,
            )

            self._append_execution_message(
                order,
                (
                    "Submission outcome is unresolved; order remains "
                    f"SUBMITTED for reconciliation: {exc}"
                ),
            )

            await db.commit()

            return await self._reload_order(order.id)

        self._apply_execution_result(
            order,
            result,
        )

        # If this commit fails after broker submission, the previously
        # committed SUBMITTED state remains available for recovery.
        await db.commit()

        logger.info(
            "AQE execution result persisted. "
            "order_id=%s status=%s broker_order_id=%s "
            "broker_deal_id=%s executed_volume=%s",
            order.id,
            order.status.value,
            order.broker_order_id,
            order.broker_deal_id,
            order.executed_volume,
        )

        return await self._reload_order(order.id)

    async def _reload_order(
        self,
        order_id: UUID,
    ) -> Order:
        """
        Reload the order with its repository-defined relationships
        so API serialization does not rely on implicit async loading.
        """

        order = await self.order_repository.get_by_id(
            order_id,
        )

        if order is None:
            raise RuntimeError(
                f"Order {order_id} disappeared after execution."
            )

        return order

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @staticmethod
    def _validate_order_state(
        order: Order,
    ) -> None:
        """
        Restrict initial submission to CREATED orders.

        Uncertain submissions and partial fills must be handled by
        recovery/reconciliation, never by resubmitting this order.
        """

        if order.status != OrderStatus.CREATED:
            raise ValueError(
                "Only CREATED orders may be submitted. "
                f"Current order status is {order.status.value}."
            )

    # ==========================================================
    # BROKER SYMBOL RESOLUTION
    # ==========================================================

    async def _resolve_broker_symbol(
        self,
        order: Order,
    ) -> str:
        """
        Resolve the account-specific broker-native instrument.
        """

        if order.account_id is None:
            raise ValueError(
                "Order trading account is unavailable."
            )

        if order.symbol_id is None:
            raise ValueError(
                "Order symbol is unavailable."
            )

        account_symbol = (
            await self.account_symbol_repository
            .get_by_account_and_symbol(
                account_id=order.account_id,
                symbol_id=order.symbol_id,
            )
        )

        if account_symbol is None:
            raise ValueError(
                "Symbol is not configured for the selected account."
            )

        broker_symbol = (
            account_symbol.broker_symbol.strip()
            if account_symbol.broker_symbol
            else ""
        )

        if not broker_symbol:
            raise ValueError(
                "The account symbol has no broker-native symbol."
            )

        return broker_symbol

    # ==========================================================
    # EXECUTION ORDER
    # ==========================================================

    @staticmethod
    def _build_execution_order(
        order: Order,
        broker_symbol: str,
    ) -> ExecutionOrder:
        """
        Convert the persisted order into a broker-independent request.
        """

        if order.account_id is None:
            raise ValueError(
                "Order trading account is unavailable."
            )

        if order.symbol_id is None:
            raise ValueError(
                "Order symbol is unavailable."
            )

        broker_symbol = broker_symbol.strip()

        if not broker_symbol:
            raise ValueError(
                "Broker symbol cannot be empty."
            )

        order_type = OrderType(order.order_type.value)
        side = OrderSide(order.side.value)

        price: Decimal | None = None

        if order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            price = order.requested_price

            if price is None or price <= 0:
                raise ValueError(
                    "Pending orders require a positive requested price."
                )

        return ExecutionOrder(
            symbol=broker_symbol,
            account_id=order.account_id,
            side=side,
            order_type=order_type,
            volume=order.volume,
            price=price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            comment=order.comment,
        )

    # ==========================================================
    # RESULT PROCESSING
    # ==============================================================

    def _apply_execution_result(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Apply a normalized result without assuming unconfirmed fills.
        """

        status = result.status

        # A bridge-confirmed NOT_SUBMITTED outcome indicates the MT5
        # submission boundary was not crossed, making a later explicit
        # user retry safe.
        if status == ExecutionStatus.NOT_SUBMITTED:
            order.status = OrderStatus.CREATED

            self._append_execution_message(
                order,
                result.message or (
                    "Bridge confirmed that the order was not submitted."
                ),
            )
            return

        # For all outcomes except NOT_SUBMITTED, preserve identifiers
        # that the broker explicitly returned. They can help recovery
        # even if execution itself has not been confirmed.
        self._apply_broker_identifiers(
            order,
            result,
        )

        if status == ExecutionStatus.REJECTED:
            order.status = OrderStatus.REJECTED

            self._append_execution_message(
                order,
                result.message or "Broker confirmed order rejection.",
            )
            return

        if status == ExecutionStatus.PLACED:
            self._handle_placed_result(
                order,
                result,
            )
            return

        if status == ExecutionStatus.PARTIALLY_FILLED:
            self._apply_confirmed_fill(
                order,
                result,
                partial_claimed=True,
            )
            return

        if status == ExecutionStatus.SUCCESS:
            self._handle_success(
                order,
                result,
            )
            return

        # UNKNOWN and legacy FAILED are not proof of rejection.
        # Keep SUBMITTED so the reconciliation service can investigate.
        order.status = OrderStatus.SUBMITTED

        self._append_execution_message(
            order,
            result.message or (
                "Broker execution outcome is unconfirmed; "
                "reconciliation is required."
            ),
        )

    def _handle_placed_result(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Handle broker acceptance without confirmed execution.
        """

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            if result.broker_order_id is None:
                # No broker ticket means the accepted order cannot be
                # identified confidently for later operations.
                order.status = OrderStatus.SUBMITTED

                self._append_execution_message(
                    order,
                    (
                        "Broker reported a pending order was placed "
                        "without an order ID; reconciliation is required."
                    ),
                )
                return

            order.status = OrderStatus.PENDING

            self._append_execution_message(
                order,
                result.message or "Pending order accepted by broker.",
            )
            return

        # A market-order PLACED response is not proof of a deal/fill.
        # Retain SUBMITTED so reconciliation continues to track it.
        order.status = OrderStatus.SUBMITTED

        self._append_execution_message(
            order,
            result.message or (
                "Broker placed the market order, but execution "
                "has not yet been confirmed."
            ),
        )

    def _handle_success(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Handle SUCCESS only when its execution data is sufficient.

        For a pending order, a successful placement without deal
        evidence remains PENDING rather than being marked FILLED.
        """

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            has_execution_evidence = (
                result.broker_deal_id is not None
                and result.volume is not None
                and result.price is not None
            )

            if not has_execution_evidence:
                if result.broker_order_id is not None:
                    order.status = OrderStatus.PENDING
                else:
                    order.status = OrderStatus.SUBMITTED

                return

        self._apply_confirmed_fill(
            order,
            result,
            partial_claimed=False,
        )

    def _apply_confirmed_fill(
        self,
        order: Order,
        result: ExecutionResult,
        *,
        partial_claimed: bool,
    ) -> None:
        """
        Persist only a positive, broker-confirmed execution quantity
        and execution price.

        A contradictory or incomplete result remains SUBMITTED and
        must be resolved through reconciliation.
        """

        volume = result.volume
        price = result.price

        has_broker_identity = (
            result.broker_deal_id is not None
            or result.broker_order_id is not None
        )

        if (
            not has_broker_identity
            or volume is None
            or price is None
            or volume <= 0
            or price <= 0
        ):
            order.status = OrderStatus.SUBMITTED

            self._append_execution_message(
                order,
                (
                    "Execution result lacks sufficient confirmed "
                    "identity, volume or price; reconciliation is required."
                ),
            )
            return

        requested_volume = order.volume

        if requested_volume <= 0 or volume > requested_volume:
            order.status = OrderStatus.SUBMITTED

            self._append_execution_message(
                order,
                (
                    "Broker execution volume conflicts with the "
                    "requested volume; reconciliation is required."
                ),
            )
            return

        if volume < requested_volume:
            # A broker result labelled SUCCESS can still reveal that
            # the actual executed quantity was smaller than requested.
            order.status = OrderStatus.PARTIALLY_FILLED

        elif partial_claimed:
            # A PARTIALLY_FILLED status with a complete volume is
            # contradictory. Do not guess which representation wins.
            order.status = OrderStatus.SUBMITTED

            self._append_execution_message(
                order,
                (
                    "Broker partial-fill status conflicts with the "
                    "reported executed volume; reconciliation is required."
                ),
            )
            return

        else:
            order.status = OrderStatus.FILLED

        # These fields represent confirmed cumulative execution data.
        order.executed_volume = volume
        order.executed_price = price

        if result.message:
            self._append_execution_message(
                order,
                result.message,
            )

    # ==========================================================
    # BROKER IDENTIFIERS
    # ==========================================================

    @staticmethod
    def _apply_broker_identifiers(
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Store identifiers independently and preserve identifiers
        that were already recorded.
        """

        if result.broker_order_id is not None:
            order.broker_order_id = result.broker_order_id

        if result.broker_deal_id is not None:
            order.broker_deal_id = result.broker_deal_id

        if result.broker_position_id is not None:
            order.broker_position_id = result.broker_position_id

    # ==========================================================
    # MESSAGE HANDLING
    # ==========================================================

    @staticmethod
    def _append_execution_message(
        order: Order,
        message: str | None,
    ) -> None:
        """
        Append execution diagnostics while respecting the database
        comment column's 255-character limit.
        """

        if not message:
            return

        message = str(message).strip()

        if not message:
            return

        marker = "[execution] "

        existing = (order.comment or "").strip()
        suffix = f"{marker}{message}"

        # Avoid repeatedly appending the exact same diagnostic.
        if suffix in existing:
            return

        if existing:
            combined = f"{existing} | {suffix}"
        else:
            combined = suffix

        # Keep the persisted value within String(255).
        order.comment = combined[:255]
