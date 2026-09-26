from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import OrderStatus
from app.database.models.order import Order


class OrderRepository:
    """
    Persistence layer for AQE orders.

    Broker identifiers are treated as separate entities:

        broker_order_id
        broker_deal_id
        broker_position_id

    The execution_correlation_id is the AQE-owned correlation key
    connecting a RiskDecision to its persisted Order.

    Relationship loading required by higher-level services is handled
    explicitly here so async SQLAlchemy never relies on implicit
    lazy-loading.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------

    async def create(
        self,
        order: Order,
    ) -> Order:
        """
        Persist a new order.
        """

        self.db.add(order)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def get_by_id(
        self,
        order_id: UUID,
    ) -> Order | None:
        """
        Retrieve an order by AQE UUID.
        """

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

    async def get_by_id_for_update(
        self,
        order_id: UUID,
    ) -> Order | None:
        """
        Retrieve and lock an order for execution/update.

        The row lock prevents two execution requests from submitting
        the same persisted order concurrently.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(Order.id == order_id)
            .with_for_update()
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Execution correlation lookup
    # ------------------------------------------------------------------

    async def get_by_execution_correlation_id(
        self,
        execution_correlation_id: UUID,
    ) -> Order | None:
        """
        Retrieve an AQE order by its execution correlation ID.

        This is the primary lookup used to correlate execution results
        back to the AQE order that originated the broker submission.

        The lookup intentionally does not depend on:

            - broker symbol
            - broker order ID
            - broker deal ID
            - broker position ID
            - strategy name
            - order timing
            - volume

        Those fields can be used for validation, but they are not the
        primary execution correlation mechanism.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.execution_correlation_id
                == execution_correlation_id
            )
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Broker identifier lookups
    # ------------------------------------------------------------------

    async def get_by_broker_order_id(
        self,
        broker_order_id: int,
    ) -> Order | None:
        """
        Retrieve an AQE order by broker order/ticket ID.

        The account relationship is loaded because execution and
        reconciliation services may need to verify ownership.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_order_id == broker_order_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker_deal_id(
        self,
        broker_deal_id: int,
    ) -> Order | None:
        """
        Retrieve an AQE order by broker deal/execution ID.

        The account relationship is loaded because execution and
        reconciliation services may need to verify ownership.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_deal_id == broker_deal_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker_position_id(
        self,
        broker_position_id: int,
    ) -> Order | None:
        """
        Retrieve an AQE order by broker position ID.

        The account relationship is loaded because position
        synchronization may need to verify ownership.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_position_id
                == broker_position_id
            )
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Backwards-compatible broker order lookup
    # ------------------------------------------------------------------

    async def get_by_ticket(
        self,
        ticket: int,
    ) -> Order | None:
        """
        Backwards-compatible alias for broker order lookup.

        New code should use get_by_broker_order_id().
        """

        return await self.get_by_broker_order_id(ticket)

    # ------------------------------------------------------------------
    # General queries
    # ------------------------------------------------------------------

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders with pagination.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def get_by_account(
        self,
        account_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders belonging to a trading account.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.account_id == account_id
            )
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def get_by_symbol(
        self,
        symbol_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders for a symbol.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.symbol_id == symbol_id
            )
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def get_by_status(
        self,
        status: OrderStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders by lifecycle status.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.status == status
            )
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def get_pending_orders(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders awaiting broker execution/submission.

        CREATED:
            Not yet submitted.

        PENDING:
            Broker accepted a pending order and it is awaiting
            execution.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.status.in_(
                    (
                        OrderStatus.CREATED,
                        OrderStatus.PENDING,
                    )
                )
            )
            .order_by(Order.created_at.asc())
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        order: Order,
    ) -> Order:
        """
        Persist changes to an existing order.
        """

        self.db.add(order)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def update_status(
        self,
        order: Order,
        status: OrderStatus,
    ) -> Order:
        """
        Update only the lifecycle status of an order.
        """

        order.status = status

        self.db.add(order)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(
        self,
        order: Order,
    ) -> None:
        """
        Delete an order from persistence.
        """

        await self.db.delete(order)

        await self.db.commit()