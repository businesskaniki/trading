from uuid import UUID

from app.core.constants import OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderUpdate


class OrderService:
    """
    Business logic layer for Orders.
    """

    def __init__(
        self,
        repository: OrderRepository,
    ):
        self.repository = repository


    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create_order(
        self,
        data: OrderCreate,
    ):

        existing_order = None

        if data.ticket:
            existing_order = await self.repository.get_by_ticket(
                data.ticket
            )

        if existing_order:
            raise ValueError(
                "Order with this ticket already exists"
            )

        return await self.repository.create(
            **data.model_dump()
        )


    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

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


    async def get_orders(self):

        return await self.repository.get_all()


    async def get_account_orders(
        self,
        account_id: UUID,
    ):

        return await self.repository.get_by_account(
            account_id
        )


    async def get_symbol_orders(
        self,
        symbol_id: UUID,
    ):

        return await self.repository.get_by_symbol(
            symbol_id
        )


    async def get_status_orders(
        self,
        status: OrderStatus,
    ):

        return await self.repository.get_by_status(
            status
        )


    async def get_pending_orders(self):

        return await self.repository.get_pending_orders()


    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update_order(
        self,
        order_id: UUID,
        data: OrderUpdate,
    ):

        order = await self.get_order(
            order_id
        )

        return await self.repository.update(
            order,
            **data.model_dump(
                exclude_unset=True
            )
        )


    async def update_order_status(
        self,
        order_id: UUID,
        status: OrderStatus,
    ):

        order = await self.get_order(
            order_id
        )


        # Prevent invalid state changes
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
            status
        )


    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete_order(
        self,
        order_id: UUID,
    ):

        order = await self.get_order(
            order_id
        )


        if order.status == OrderStatus.FILLED:
            raise ValueError(
                "Filled orders cannot be deleted"
            )


        await self.repository.delete(
            order
        )