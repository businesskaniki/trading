# app/repositories/order_repository.py

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.order import Order
from app.core.constants import OrderStatus


class OrderRepository:
    """
    Repository responsible for Order database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create(self, **data) -> Order:
        order = Order(**data)

        self.db.add(order)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(self, order_id: UUID) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(Order.id == order_id)
        )

        return result.scalar_one_or_none()

    async def get_by_ticket(self, ticket: int) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .where(Order.ticket == ticket)
        )

        return result.scalar_one_or_none()

    async def get_all(self) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
            )
            .order_by(Order.created_at.desc())
        )

        return result.scalars().all()

    async def get_by_account(
        self,
        account_id: UUID,
    ) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(Order.account_id == account_id)
            .order_by(Order.created_at.desc())
        )

        return result.scalars().all()

    async def get_by_symbol(
        self,
        symbol_id: UUID,
    ) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(Order.symbol_id == symbol_id)
            .order_by(Order.created_at.desc())
        )

        return result.scalars().all()

    async def get_by_status(
        self,
        status: OrderStatus,
    ) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(Order.status == status)
            .order_by(Order.created_at.desc())
        )

        return result.scalars().all()

    async def get_pending_orders(self) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(
                Order.status.in_(
                    [
                        OrderStatus.CREATED,
                        OrderStatus.PENDING,
                    ]
                )
            )
            .order_by(Order.created_at)
        )

        return result.scalars().all()

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update(
        self,
        order: Order,
        **data,
    ) -> Order:

        for field, value in data.items():
            setattr(order, field, value)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def update_status(
        self,
        order: Order,
        status: OrderStatus,
    ) -> Order:

        order.status = status

        await self.db.commit()
        await self.db.refresh(order)

        return order

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    async def delete(
        self,
        order: Order,
    ) -> None:

        await self.db.delete(order)
        await self.db.commit()