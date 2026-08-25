from uuid import UUID

from app.core.constants import OrderStatus, OrderType
from app.repositories.order_repository import OrderRepository
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
)
from app.services.execution_service import ExecutionService


class OrderExecutionService:
    """
    Coordinates execution of a persisted AQE Order.

    Responsibilities:
    1. Retrieve the persisted Order.
    2. Convert it into a broker-agnostic ExecutionOrder.
    3. Execute it through ExecutionService.
    4. For MARKET orders, apply SL/TP after execution.
    5. Persist the broker execution result back to the Order.
    """

    def __init__(
        self,
        order_repository: OrderRepository,
        execution_service: ExecutionService,
    ):
        self.order_repository = order_repository
        self.execution_service = execution_service

    # ==========================================================
    # EXECUTE ORDER
    # ==========================================================

    async def execute_order(
        self,
        order_id: UUID,
    ):
        """
        Execute an existing database Order.

        MARKET:
            1. Execute without SL/TP.
            2. Apply SL/TP after execution.

        LIMIT / STOP:
            1. Execute using requested price.
            2. SL/TP remain part of the initial request.
        """

        # ------------------------------------------------------
        # 1. Retrieve order
        # ------------------------------------------------------

        order = await self.order_repository.get_by_id(
            order_id
        )

        if not order:
            raise ValueError("Order not found")

        # ------------------------------------------------------
        # 2. Validate order status
        # ------------------------------------------------------

        if order.status == OrderStatus.FILLED:
            raise ValueError(
                "Order has already been filled"
            )

        if order.status == OrderStatus.CANCELLED:
            raise ValueError(
                "Cancelled orders cannot be executed"
            )

        # ------------------------------------------------------
        # 3. Resolve broker symbol
        # ------------------------------------------------------

        if not order.symbol:
            raise ValueError(
                "Order does not have a valid symbol"
            )

        broker_symbol = order.symbol.broker_symbol

        if not broker_symbol:
            raise ValueError(
                "Order symbol does not have a broker symbol"
            )

        # ------------------------------------------------------
        # 4. Preserve requested stops
        # ------------------------------------------------------

        requested_stop_loss = order.stop_loss
        requested_take_profit = order.take_profit

        # ------------------------------------------------------
        # 5. Build ExecutionOrder
        # ------------------------------------------------------
        #
        # MARKET:
        #   price = None
        #   SL/TP = None
        #
        # LIMIT / STOP:
        #   price = requested_price
        #   SL/TP = requested values
        #
        # ------------------------------------------------------

        is_market = (
            order.order_type == OrderType.MARKET
        )

        execution_order = ExecutionOrder(
            symbol=broker_symbol,
            side=order.side,
            order_type=order.order_type,
            volume=order.volume,
            price=(
                None
                if is_market
                else order.requested_price
            ),
            stop_loss=(
                None
                if is_market
                else requested_stop_loss
            ),
            take_profit=(
                None
                if is_market
                else requested_take_profit
            ),
            comment=order.comment or "AQE",
        )

        # ------------------------------------------------------
        # 6. Execute through ExecutionService
        # ------------------------------------------------------

        result: ExecutionResult = (
            await self.execution_service.execute_order(
                execution_order
            )
        )

        # ------------------------------------------------------
        # 7. Check execution result
        # ------------------------------------------------------

        if result.status.value != "SUCCESS":

            if result.status.value in {
                "REJECTED",
                "FAILED",
            }:
                order.status = OrderStatus.REJECTED

                await self.order_repository.update(order)

            return order

        # ------------------------------------------------------
        # 8. Validate broker ticket
        # ------------------------------------------------------

        if result.order_id is None:
            raise ValueError(
                "Broker execution succeeded but "
                "no broker ticket was returned"
            )

        # ------------------------------------------------------
        # 9. For MARKET orders, apply SL/TP separately
        # ------------------------------------------------------

        if is_market and (
            requested_stop_loss is not None
            or requested_take_profit is not None
        ):

            await self.execution_service.modify_position(
                position_id=result.order_id,
                sl=(
                    float(requested_stop_loss)
                    if requested_stop_loss is not None
                    else None
                ),
                tp=(
                    float(requested_take_profit)
                    if requested_take_profit is not None
                    else None
                ),
            )

        # ------------------------------------------------------
        # 10. Update database Order
        # ------------------------------------------------------

        order.ticket = result.order_id
        order.executed_price = result.price
        order.status = OrderStatus.FILLED

        # ------------------------------------------------------
        # 11. Persist
        # ------------------------------------------------------

        return await self.order_repository.update(
            order
        )