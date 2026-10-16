
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
            Broker order/ticket identifier.

        broker_deal_id
            Representative broker deal identifier stored on the order.

        broker_position_id
            Broker position identifier associated with the order.

    The execution_correlation_id is the AQE-owned correlation key
    connecting a RiskDecision to its persisted Order.

    Volume semantics:

        volume
            Original volume requested by the Risk Engine.

        executed_volume
            Cumulative broker-confirmed executed volume.

    Relationship loading required by higher-level services is handled
    explicitly so asynchronous SQLAlchemy code does not rely on
    implicit lazy-loading.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # CREATE / READ
    # ------------------------------------------------------------------

    async def create(
        self,
        order: Order,
    ) -> Order:
        """
        Persist a new order and return the refreshed ORM entity.
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
        Retrieve an order by its AQE UUID.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.id == order_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        order_id: UUID,
    ) -> Order | None:
        """
        Retrieve and lock an order for execution or update.

        The row lock serializes concurrent updates to the same order
        while the surrounding database transaction remains active.

        The caller must commit or roll back the transaction and must
        enforce the permitted order-state transition.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.id == order_id,
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # EXECUTION CORRELATION LOOKUP
    # ------------------------------------------------------------------

    async def get_by_execution_correlation_id(
        self,
        execution_correlation_id: UUID,
    ) -> Order | None:
        """
        Retrieve an order by its unique AQE execution correlation ID.

        Broker identifiers, symbols, timing, volume and strategy names
        are not used as substitutes for this AQE-owned correlation key.
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
                == execution_correlation_id,
            )
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # BROKER IDENTIFIER LOOKUPS
    # ------------------------------------------------------------------

    async def get_by_broker_order_id(
        self,
        broker_order_id: int,
    ) -> Order | None:
        """
        Retrieve an order by broker order/ticket ID.

        This lookup follows the existing database uniqueness contract.
        Callers operating across multiple broker accounts must also
        validate that the matched order belongs to the expected account.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_order_id == broker_order_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker_deal_id(
        self,
        broker_deal_id: int,
    ) -> Order | None:
        """
        Retrieve an order by its stored broker deal ID.

        This identifies an order's representative deal, not a complete
        ledger of every deal contributing to a partial or full fill.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_deal_id == broker_deal_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_broker_position_id(
        self,
        broker_position_id: int,
    ) -> Order | None:
        """
        Retrieve an order associated with a broker position ID.

        Position synchronization must account for broker positions
        that may be associated with more than one order.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.broker_position_id == broker_position_id,
            )
        )

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # BACKWARDS-COMPATIBLE BROKER ORDER LOOKUP
    # ------------------------------------------------------------------

    async def get_by_ticket(
        self,
        ticket: int,
    ) -> Order | None:
        """
        Backwards-compatible alias for broker order lookup.

        New code should use get_by_broker_order_id().
        """

        return await self.get_by_broker_order_id(
            ticket,
        )

    # ------------------------------------------------------------------
    # GENERAL QUERIES
    # ------------------------------------------------------------------

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders with pagination, newest first.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .order_by(
                Order.created_at.desc(),
            )
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
        Retrieve orders belonging to one trading account.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.account_id == account_id,
            )
            .order_by(
                Order.created_at.desc(),
            )
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
        Retrieve orders for a canonical AQE symbol.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.symbol_id == symbol_id,
            )
            .order_by(
                Order.created_at.desc(),
            )
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
                Order.status == status,
            )
            .order_by(
                Order.created_at.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    # ------------------------------------------------------------------
    # PENDING ORDER LIST
    # ------------------------------------------------------------------

    async def get_pending_orders(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """
        Retrieve orders in CREATED or PENDING states.

        CREATED:
            An AQE order eligible for initial submission, subject to
            the execution service's validation.

        PENDING:
            An order accepted by the broker that is awaiting execution.

        IMPORTANT:
            PENDING orders must not be resubmitted as new orders.
            They are included here for listing and monitoring purposes.
            Only CREATED orders are eligible for initial submission.
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
            .order_by(
                Order.created_at.asc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    # ------------------------------------------------------------------
    # ORDER RECONCILIATION
    # ------------------------------------------------------------------

    async def get_orders_requiring_reconciliation(
        self,
        account_id: UUID,
    ) -> list[Order]:
        """
        Retrieve account orders that require broker-state monitoring.

        SUBMITTED:
            The broker submission outcome is unresolved.

        PENDING:
            The broker accepted an order, but it may subsequently fill,
            be cancelled or expire.

        PARTIALLY_FILLED:
            Some volume has executed, and additional fills or a terminal
            order state may still arrive.

        Terminal states such as FILLED, CANCELLED, REJECTED and EXPIRED
        are excluded from this active-order reconciliation query.

        Orders are returned oldest-first so the longest-outstanding
        orders are processed first.
        """

        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.account),
                selectinload(Order.symbol),
                selectinload(Order.position),
            )
            .where(
                Order.account_id == account_id,
                Order.status.in_(
                    (
                        OrderStatus.SUBMITTED,
                        OrderStatus.PENDING,
                        OrderStatus.PARTIALLY_FILLED,
                    )
                ),
            )
            .order_by(
                Order.created_at.asc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    async def update(
        self,
        order: Order,
    ) -> Order:
        """
        Persist updates to an existing order.

        This method owns its transaction commit. Use direct ORM changes
        and the caller-owned transaction when composing multiple writes
        into a larger atomic operation.
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

        This method commits the change. Callers must validate that the
        transition is legal before invoking it.
        """

        order.status = status

        self.db.add(order)

        await self.db.commit()
        await self.db.refresh(order)

        return order

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete(
        self,
        order: Order,
    ) -> None:
        """
        Delete an order from persistence.

        Order deletion should only be used where the application's
        retention and referential-integrity rules permit it.
        """

        await self.db.delete(order)

        await self.db.commit()
