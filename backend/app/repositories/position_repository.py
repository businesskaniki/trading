from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import PositionStatus
from app.database.models.position import Position


class PositionRepository:
    """
    Repository responsible for Position database operations.

    This layer performs persistence and retrieval only.

    Risk aggregation methods are included here because they are
    database-level queries required to construct the server-side
    RiskState.

    Business decisions still belong to the Risk Engine.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create(
        self,
        **data,
    ) -> Position:

        position = Position(**data)

        self.db.add(position)

        await self.db.commit()
        await self.db.refresh(position)

        return position

    # ==========================================================
    # READ
    # ==========================================================

    async def get_by_id(
        self,
        position_id: UUID,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
                selectinload(Position.trade),
            )
            .where(Position.id == position_id)
        )

        return result.scalar_one_or_none()

    # ----------------------------------------------------------
    # Broker ticket
    # ----------------------------------------------------------

    async def get_by_ticket(
        self,
        ticket: int,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position).options(selectinload(Position.account)).where(Position.ticket == ticket)
        )

        return result.scalar_one_or_none()

    # ----------------------------------------------------------
    # Order
    # ----------------------------------------------------------

    async def get_by_order(
        self,
        order_id: UUID,
    ) -> Position | None:

        result = await self.db.execute(
            select(Position).where(Position.order_id == order_id)
        )

        return result.scalar_one_or_none()

    # ----------------------------------------------------------
    # Account
    # ----------------------------------------------------------

    async def get_by_account(
        self,
        account_id: UUID,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.symbol),
                selectinload(Position.order),
            )
            .where(Position.account_id == account_id)
            .order_by(Position.opened_at.desc())
        )

        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Symbol
    # ----------------------------------------------------------

    async def get_by_symbol(
        self,
        symbol_id: UUID,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.order),
            )
            .where(Position.symbol_id == symbol_id)
            .order_by(Position.opened_at.desc())
        )

        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    async def get_by_status(
        self,
        position_status: PositionStatus,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
            )
            .where(Position.status == position_status)
            .order_by(Position.opened_at.desc())
        )

        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Open positions
    # ----------------------------------------------------------

    async def get_open_positions(
        self,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
            )
            .where(Position.status == PositionStatus.OPEN)
            .order_by(Position.opened_at.desc())
        )

        return list(result.scalars().all())

    # ==========================================================
    # SERVER-SIDE RISK AGGREGATION
    # ==========================================================

    # ----------------------------------------------------------
    # Open positions by account
    # ----------------------------------------------------------

    async def get_open_positions_by_account(
        self,
        account_id: UUID,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.symbol),
                selectinload(Position.order),
            )
            .where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
            .order_by(Position.opened_at.asc())
        )

        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Count open positions
    # ----------------------------------------------------------

    async def count_open_positions(
        self,
        account_id: UUID,
    ) -> int:

        result = await self.db.execute(
            select(func.count(Position.id)).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        return int(result.scalar_one())

    # ----------------------------------------------------------
    # Total current volume
    # ----------------------------------------------------------

    async def get_total_open_volume(
        self,
        account_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.current_volume),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Total initial risk
    # ----------------------------------------------------------

    async def get_total_open_risk(
        self,
        account_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.initial_risk),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Total floating P/L
    # ----------------------------------------------------------

    async def get_total_floating_profit(
        self,
        account_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.floating_profit),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Total swap
    # ----------------------------------------------------------

    async def get_total_swap(
        self,
        account_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.swap),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Total commission
    # ----------------------------------------------------------

    async def get_total_commission(
        self,
        account_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.commission),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Total notional exposure
    # ----------------------------------------------------------

    async def get_total_exposure(
        self,
        account_id: UUID,
    ) -> Decimal:

        positions = await self.get_open_positions_by_account(account_id)

        exposure = Decimal("0")

        for position in positions:

            exposure += position.current_volume * position.current_price

        return exposure

    # ----------------------------------------------------------
    # Symbol exposure
    # ----------------------------------------------------------

    async def get_symbol_exposure(
        self,
        account_id: UUID,
        symbol_id: UUID,
    ) -> Decimal:

        positions = await self.db.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol_id == symbol_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        exposure = Decimal("0")

        for position in positions.scalars().all():

            exposure += position.current_volume * position.current_price

        return exposure

    # ----------------------------------------------------------
    # Symbol volume
    # ----------------------------------------------------------

    async def get_symbol_volume(
        self,
        account_id: UUID,
        symbol_id: UUID,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.current_volume),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.symbol_id == symbol_id,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Strategy open risk
    # ----------------------------------------------------------

    async def get_strategy_open_risk(
        self,
        account_id: UUID,
        strategy: str,
    ) -> Decimal:

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Position.initial_risk),
                    Decimal("0"),
                )
            ).where(
                Position.account_id == account_id,
                Position.strategy == strategy,
                Position.status == PositionStatus.OPEN,
            )
        )

        value = result.scalar_one()

        return Decimal(str(value))

    # ----------------------------------------------------------
    # Strategy exposure
    # ----------------------------------------------------------

    async def get_strategy_exposure(
        self,
        account_id: UUID,
        strategy: str,
    ) -> Decimal:

        result = await self.db.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.strategy == strategy,
                Position.status == PositionStatus.OPEN,
            )
        )

        exposure = Decimal("0")

        for position in result.scalars().all():

            exposure += position.current_volume * position.current_price

        return exposure

    # ==========================================================
    # ALL POSITIONS
    # ==========================================================

    async def get_all(
        self,
    ) -> list[Position]:

        result = await self.db.execute(
            select(Position)
            .options(
                selectinload(Position.account),
                selectinload(Position.symbol),
                selectinload(Position.order),
                selectinload(Position.trade),
            )
            .order_by(Position.opened_at.desc())
        )

        return list(result.scalars().all())

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update(
        self,
        position: Position,
        commit: bool = True,
        **data,
    ) -> Position:

        for field, value in data.items():
            setattr(
                position,
                field,
                value,
            )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(position)

        return position

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    async def update_status(
        self,
        position: Position,
        status: PositionStatus,
        commit: bool = True,
    ) -> Position:

        position.status = status

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(position)

        return position

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        position: Position,
    ) -> None:

        await self.db.delete(position)

        await self.db.commit()
