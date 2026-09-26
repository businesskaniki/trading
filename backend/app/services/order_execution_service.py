from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.broker.exceptions import (
    BrokerConnectionError,
    BrokerDataError,
    BrokerOrderError,
    BrokerPositionError,
)
from app.database.models.order import Order
from app.repositories.order_repository import OrderRepository
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)
from app.schemas.order import OrderStatus
from app.services.execution_service import ExecutionService


class OrderExecutionService:
    """
    Orchestrates AQE order lifecycle and broker execution.

    Responsibilities:
        1. Load and lock the AQE order.
        2. Validate that the order can be executed.
        3. Resolve the broker symbol.
        4. Convert the AQE order into an ExecutionOrder.
        5. Submit the order through ExecutionService.
        6. Persist broker identifiers and execution state.

    This service does not communicate with MT5 directly.
    """

    def __init__(
        self,
        order_repository: OrderRepository,
        execution_service: ExecutionService,
    ) -> None:
        self.order_repository = order_repository
        self.execution_service = execution_service

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    async def execute_order(
        self,
        order_id: int,
        user_id,
    ) -> Order:
        """
        Execute an existing AQE order.

        The order must belong to the authenticated user and must
        still be executable.
        """

        order = await self.order_repository.get_by_id_for_update(
            order_id,
        )

        if order is None:
            raise ValueError("Order not found.")

        if order.account is None:
            raise ValueError("Order trading account is unavailable.")

        if order.account.user_id != user_id:
            raise PermissionError(
                "You do not have permission to execute this order.",
            )

        self._validate_order_state(order)
        self._validate_order_symbol(order)

        execution_order = self._build_execution_order(order)

        # Mark the AQE order as submitted before sending it to
        # the broker. The database transaction remains responsible
        # for committing the complete lifecycle transition.
        order.status = OrderStatus.SUBMITTED

        await self.order_repository.db.flush()

        try:
            result = await self.execution_service.execute_order(
                execution_order,
            )

        except (
            BrokerConnectionError,
            BrokerDataError,
            BrokerOrderError,
            BrokerPositionError,
        ) as exc:
            order.status = OrderStatus.REJECTED
            self._append_execution_message(
                order,
                str(exc),
            )

            await self.order_repository.db.flush()
            return order

        except Exception as exc:
            order.status = OrderStatus.REJECTED
            self._append_execution_message(
                order,
                f"Execution failed: {exc}",
            )

            await self.order_repository.db.flush()
            return order

        self._apply_execution_result(
            order,
            result,
        )

        await self.order_repository.db.flush()

        return order

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @staticmethod
    def _validate_order_state(
        order: Order,
    ) -> None:
        """
        Ensure the order has not already reached a terminal state.
        """

        if order.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }:
            raise ValueError(
                f"Order is already in terminal state " f"{order.status.value}.",
            )

        if order.status == OrderStatus.PENDING and order.broker_order_id is not None:
            raise ValueError(
                "Pending order has already been submitted " "to the broker.",
            )

    @staticmethod
    def _validate_order_symbol(
        order: Order,
    ) -> None:
        """
        Ensure the AQE symbol has a broker symbol available.
        """

        if order.symbol is None:
            raise ValueError(
                "Order symbol is unavailable.",
            )

        broker_symbol = getattr(
            order.symbol,
            "broker_symbol",
            None,
        )

        if not broker_symbol:
            broker_symbol = getattr(
                order.symbol,
                "symbol",
                None,
            )

        if not broker_symbol:
            raise ValueError(
                "Order symbol does not have a broker symbol.",
            )

    # ==========================================================
    # EXECUTION ORDER
    # ==========================================================

    def _build_execution_order(
        self,
        order: Order,
    ) -> ExecutionOrder:
        """
        Convert an AQE Order model into the broker-independent
        ExecutionOrder contract.
        """

        if order.symbol is None:
            raise ValueError(
                "Order symbol is unavailable.",
            )

        broker_symbol = getattr(
            order.symbol,
            "broker_symbol",
            None,
        )

        if not broker_symbol:
            broker_symbol = getattr(
                order.symbol,
                "symbol",
                None,
            )

        if not broker_symbol:
            raise ValueError(
                "Order symbol does not have a broker symbol.",
            )

        price: Decimal | None = None

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            price = order.requested_price

            if price is None:
                raise ValueError(
                    "Pending orders require a requested price.",
                )

        return ExecutionOrder(
            symbol=broker_symbol,
            account_id=order.account_id,
            side=OrderSide(order.side),
            order_type=OrderType(order.order_type),
            volume=order.volume,
            price=price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            comment=order.comment,
        )

    # ==========================================================
    # RESULT PROCESSING
    # ==========================================================

    def _apply_execution_result(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Apply broker execution information to the AQE order.
        """

        self._apply_broker_identifiers(
            order,
            result,
        )

        if result.symbol and order.symbol is not None:
            # Keep the AQE symbol relationship authoritative.
            # Broker response symbol is informational only.
            pass

        if result.price is not None:
            order.executed_price = result.price

        if result.status == ExecutionStatus.SUCCESS:
            self._handle_success(
                order,
                result,
            )
            return

        if result.status == ExecutionStatus.REJECTED:
            order.status = OrderStatus.REJECTED
            self._append_execution_message(
                order,
                result.message,
            )
            return

        # ExecutionStatus.FAILED means the broker execution did not
        # complete successfully. AQE has no FAILED order state, so
        # the execution attempt is represented as REJECTED.
        order.status = OrderStatus.REJECTED

        self._append_execution_message(
            order,
            result.message or "Broker execution failed.",
        )

    def _handle_success(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Apply successful market/pending execution lifecycle.
        """

        if order.order_type == OrderType.MARKET:
            self._handle_market_success(
                order,
                result,
            )
            return

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            self._handle_pending_success(
                order,
                result,
            )
            return

        raise ValueError(
            f"Unsupported order type: {order.order_type}.",
        )

    def _handle_market_success(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        A successful market order must have a broker execution
        identifier.

        MT5 normally provides a deal and/or order identifier.
        Position reconciliation may populate broker_position_id
        later.
        """

        if result.broker_order_id is None and result.broker_deal_id is None:
            raise ValueError(
                "Broker reported successful market execution "
                "without an order or deal identifier.",
            )

        order.status = OrderStatus.FILLED

    def _handle_pending_success(
        self,
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        A successful LIMIT/STOP submission becomes PENDING.

        A broker order ID is mandatory because the pending order
        must subsequently be identifiable for cancellation,
        modification, and reconciliation.
        """

        if result.broker_order_id is None:
            raise ValueError(
                "Broker reported successful pending order "
                "without a broker order identifier.",
            )

        order.status = OrderStatus.PENDING

    # ==========================================================
    # BROKER IDENTIFIERS
    # ==========================================================

    @staticmethod
    def _apply_broker_identifiers(
        order: Order,
        result: ExecutionResult,
    ) -> None:
        """
        Persist broker-side identifiers independently.

        AQE deliberately keeps order, deal, and position IDs
        separate because they represent different broker objects.
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
        Preserve broker/execution information in the order comment
        without replacing the original user/strategy comment.
        """

        if not message:
            return

        message = str(message).strip()

        if not message:
            return

        existing = (order.comment or "").strip()

        execution_message = f"[execution] {message}"

        if not existing:
            order.comment = execution_message
            return

        if execution_message in existing:
            return

        order.comment = f"{existing} | {execution_message}"
