from uuid import UUID

from app.core.constants import OrderStatus, OrderType
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderUpdate


class OrderService:
    """
    Business logic layer for Orders.

    The service coordinates validation and business rules
    before interacting with the repository.
    """

    def __init__(
        self,
        repository: OrderRepository,
    ):
        self.repository = repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_order(
        self,
        data: OrderCreate,
    ):

        # ------------------------------------------------------
        # Validate LIMIT / STOP price
        # ------------------------------------------------------

        if data.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        } and data.requested_price is None:

            raise ValueError(
                "requested_price is required for "
                "LIMIT and STOP orders."
            )

        # ------------------------------------------------------
        # MARKET orders should not require a requested price
        # ------------------------------------------------------

        # No broker ticket exists yet.
        #
        # The ticket is assigned after execution.

        return await self.repository.create(
            **data.model_dump()
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_order(
        self,
        order_id: UUID,
    ):

        order = await self.repository.get_by_id(
            order_id
        )

        if not order:
            raise ValueError(
                "Order not found"
            )

        return order

    # ----------------------------------------------------------
    # All orders
    # ----------------------------------------------------------

    async def get_orders(self):

        return await self.repository.get_all()

    # ----------------------------------------------------------
    # Account orders
    # ----------------------------------------------------------

    async def get_account_orders(
        self,
        account_id: UUID,
    ):

        return await self.repository.get_by_account(
            account_id
        )

    # ----------------------------------------------------------
    # Symbol orders
    # ----------------------------------------------------------

    async def get_symbol_orders(
        self,
        symbol_id: UUID,
    ):

        return await self.repository.get_by_symbol(
            symbol_id
        )

    # ----------------------------------------------------------
    # Status orders
    # ----------------------------------------------------------

    async def get_status_orders(
        self,
        status: OrderStatus,
    ):

        return await self.repository.get_by_status(
            status
        )

    # ----------------------------------------------------------
    # Pending orders
    # ----------------------------------------------------------

    async def get_pending_orders(self):

        return await self.repository.get_pending_orders()

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_order(
        self,
        order_id: UUID,
        data: OrderUpdate,
    ):

        order = await self.get_order(
            order_id
        )

        # ------------------------------------------------------
        # Filled orders cannot be modified
        # ------------------------------------------------------

        if order.status == OrderStatus.FILLED:

            raise ValueError(
                "Filled orders cannot be modified"
            )

        # ------------------------------------------------------
        # Cancelled orders cannot be modified
        # ------------------------------------------------------

        if order.status == OrderStatus.CANCELLED:

            raise ValueError(
                "Cancelled orders cannot be modified"
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        # ------------------------------------------------------
        # Validate order type / price combination
        # ------------------------------------------------------

        new_order_type = update_data.get(
            "order_type",
            order.order_type,
        )

        new_requested_price = update_data.get(
            "requested_price",
            order.requested_price,
        )

        if new_order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        } and new_requested_price is None:

            raise ValueError(
                "requested_price is required for "
                "LIMIT and STOP orders."
            )

        return await self.repository.update(
            order,
            **update_data
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    async def update_order_status(
        self,
        order_id: UUID,
        status: OrderStatus,
    ):

        order = await self.get_order(
            order_id
        )

        # ------------------------------------------------------
        # Terminal states
        # ------------------------------------------------------

        if order.status == OrderStatus.FILLED:

            raise ValueError(
                "Filled orders cannot be modified"
            )

        if order.status == OrderStatus.CANCELLED:

            raise ValueError(
                "Cancelled orders cannot be modified"
            )

        return await self.repository.update_status(
            order,
            status,
        )

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_order(
        self,
        order_id: UUID,
    ):

        order = await self.get_order(
            order_id
        )

        # ------------------------------------------------------
        # Filled orders
        # ------------------------------------------------------

        if order.status == OrderStatus.FILLED:

            raise ValueError(
                "Filled orders cannot be deleted"
            )

        # ------------------------------------------------------
        # Executing orders
        # ------------------------------------------------------

        if order.status == OrderStatus.EXECUTING:

            raise ValueError(
                "Executing orders cannot be deleted"
            )

        # ------------------------------------------------------
        # Delete
        # ------------------------------------------------------

        await self.repository.delete(
            order
        )