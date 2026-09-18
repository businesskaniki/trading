from uuid import UUID

from app.core.constants import OrderStatus, OrderType
from app.repositories.order_repository import OrderRepository
from app.repositories.trading_account_repository import TradingAccountRepository
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
        account_repository: TradingAccountRepository | None = None,
    ):
        self.repository = repository
        self.account_repository = account_repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_order(
        self,
        data: OrderCreate,
        user_id: UUID | None = None,
    ):

        if user_id is not None and self.account_repository is not None:
            account = await self.account_repository.get_by_id_and_user(data.account_id, user_id)
            if account is None:
                raise ValueError("Trading account not found")

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
        user_id: UUID | None = None,
    ):

        order = await self.repository.get_by_id(
            order_id
        )

        if not order:
            raise ValueError(
                "Order not found"
            )

        if user_id is not None and order.account.user_id != user_id:
            raise ValueError("Order not found")

        return order

    # ----------------------------------------------------------
    # All orders
    # ----------------------------------------------------------

    async def get_orders(self, user_id: UUID | None = None):

        orders = await self.repository.get_all()
        if user_id is not None:
            return [order for order in orders if order.account.user_id == user_id]
        return orders

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
        user_id: UUID | None = None,
    ):

        order = await self.get_order(order_id, user_id=user_id)

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
        user_id: UUID | None = None,
    ):

        order = await self.get_order(order_id, user_id=user_id)

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
        user_id: UUID | None = None,
    ):

        order = await self.get_order(order_id, user_id=user_id)

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