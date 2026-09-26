from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.constants import OrderStatus, OrderType
from app.database.models.order import Order
from app.repositories.order_repository import OrderRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.order import (
    OrderCreate,
    OrderStatusUpdate,
    OrderUpdate,
)


class OrderService:
    """
    Business service for persisted AQE orders.

    This service manages order creation and general CRUD operations.

    Broker execution itself belongs to OrderExecutionService.
    """

    def __init__(
        self,
        order_repository: OrderRepository,
        trading_account_repository: TradingAccountRepository | None = None,
    ):
        self.order_repository = order_repository
        self.trading_account_repository = trading_account_repository

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_order(
        self,
        data: OrderCreate,
        user_id: UUID | None = None,
    ) -> Order:
        """
        Create a new AQE order.

        The order starts in CREATED state and has no broker identifiers.
        """

        if self.trading_account_repository is not None:
            account = await self.trading_account_repository.get_by_id(data.account_id)

            if account is None:
                raise ValueError("Trading account not found")

            if user_id is not None and account.user_id != user_id:
                raise ValueError("Trading account not found")

        # --------------------------------------------------------------
        # Order-type validation
        # --------------------------------------------------------------

        if (
            data.order_type
            in {
                OrderType.LIMIT,
                OrderType.STOP,
            }
            and data.requested_price is None
        ):
            raise ValueError("requested_price is required for LIMIT and STOP orders.")

        # --------------------------------------------------------------
        # Create entity
        # --------------------------------------------------------------

        order = Order(
            strategy=data.strategy,
            comment=data.comment,
            account_id=data.account_id,
            symbol_id=data.symbol_id,
            order_type=data.order_type,
            side=data.side,
            volume=data.volume,
            requested_price=data.requested_price,
            stop_loss=data.stop_loss,
            take_profit=data.take_profit,
            status=OrderStatus.CREATED,
        )

        return await self.order_repository.create(order)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_order(
        self,
        order_id: UUID,
        user_id: UUID | None = None,
    ) -> Order:
        """
        Retrieve an order and optionally enforce account ownership.
        """

        order = await self.order_repository.get_by_id(order_id)

        if order is None:
            raise ValueError("Order not found")

        if user_id is not None:
            if not order.account:
                raise ValueError("Order not found")

            if order.account.user_id != user_id:
                raise ValueError("Order not found")

        return order

    async def get_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        user_id: UUID | None = None,
    ):
        """
        Retrieve orders.

        When user_id is provided, only orders belonging to that user's
        trading accounts should be returned.
        """

        if user_id is None:
            return await self.order_repository.get_all(
                skip=skip,
                limit=limit,
            )

        if self.trading_account_repository is None:
            return await self.order_repository.get_all(
                skip=skip,
                limit=limit,
            )

        accounts = await self.trading_account_repository.get_by_user_id(user_id)

        orders = []

        for account in accounts:
            account_orders = await self.order_repository.get_by_account(
                account.id,
                skip=skip,
                limit=limit,
            )
            orders.extend(account_orders)

        orders.sort(
            key=lambda order: order.created_at,
            reverse=True,
        )

        return orders[:limit]

    async def get_orders_by_account(
        self,
        account_id: UUID,
        skip: int = 0,
        limit: int = 100,
        user_id: UUID | None = None,
    ):
        """
        Retrieve orders belonging to an account.
        """

        if user_id is not None:
            if self.trading_account_repository is None:
                raise ValueError("Trading account not found")

            account = await self.trading_account_repository.get_by_id(account_id)

            if account is None or account.user_id != user_id:
                raise ValueError("Trading account not found")

        return await self.order_repository.get_by_account(
            account_id,
            skip=skip,
            limit=limit,
        )

    async def get_orders_by_symbol(
        self,
        symbol_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ):
        """
        Retrieve orders for a symbol.
        """

        return await self.order_repository.get_by_symbol(
            symbol_id,
            skip=skip,
            limit=limit,
        )

    async def get_orders_by_status(
        self,
        status: OrderStatus,
        skip: int = 0,
        limit: int = 100,
    ):
        """
        Retrieve orders by lifecycle status.
        """

        return await self.order_repository.get_by_status(
            status,
            skip=skip,
            limit=limit,
        )

    async def get_pending_orders(
        self,
        skip: int = 0,
        limit: int = 100,
    ):
        """
        Retrieve orders awaiting submission or broker execution.
        """

        return await self.order_repository.get_pending_orders(
            skip=skip,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_order(
        self,
        order_id: UUID,
        data: OrderUpdate,
        user_id: UUID | None = None,
    ) -> Order:
        """
        Update mutable order fields.

        Orders that have already reached the broker are not freely
        editable through this CRUD service.
        """

        order = await self.get_order(
            order_id=order_id,
            user_id=user_id,
        )

        if order.status not in {
            OrderStatus.CREATED,
        }:
            raise ValueError("Only CREATED orders can be updated")

        updates = data.model_dump(
            exclude_unset=True,
        )

        if not updates:
            return order

        # --------------------------------------------------------------
        # Validate resulting order type / requested price
        # --------------------------------------------------------------

        resulting_order_type = updates.get(
            "order_type",
            order.order_type,
        )

        resulting_requested_price = updates.get(
            "requested_price",
            order.requested_price,
        )

        if (
            resulting_order_type
            in {
                OrderType.LIMIT,
                OrderType.STOP,
            }
            and resulting_requested_price is None
        ):
            raise ValueError("requested_price is required for LIMIT and STOP orders.")

        for field, value in updates.items():
            setattr(order, field, value)

        return await self.order_repository.update(order)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def update_status(
        self,
        order_id: UUID,
        data: OrderStatusUpdate,
        user_id: UUID | None = None,
    ) -> Order:
        """
        Update order status for administrative/internal workflows.

        Broker-driven execution transitions should normally be handled
        by OrderExecutionService rather than this method.
        """

        order = await self.get_order(
            order_id=order_id,
            user_id=user_id,
        )

        if order.status == OrderStatus.FILLED:
            raise ValueError("Filled orders cannot have their status changed")

        if order.status == OrderStatus.CANCELLED:
            raise ValueError("Cancelled orders cannot have their status changed")

        if order.status == OrderStatus.REJECTED:
            raise ValueError("Rejected orders cannot have their status changed")

        order.status = data.status

        return await self.order_repository.update(order)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_order(
        self,
        order_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        """
        Delete an order only while it remains local to AQE.

        Once submitted to the broker, the order must be cancelled through
        the appropriate broker/execution workflow instead of simply
        deleting the database record.
        """

        order = await self.get_order(
            order_id=order_id,
            user_id=user_id,
        )

        if order.status not in {
            OrderStatus.CREATED,
        }:
            raise ValueError("Only CREATED orders can be deleted")

        await self.order_repository.delete(order)
