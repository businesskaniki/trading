from datetime import datetime, timezone
from uuid import UUID

from app.core.constants import PositionStatus
from app.repositories.position_repository import PositionRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.position import PositionCreate, PositionUpdate


class PositionService:
    """
    Business logic layer for Positions.

    This service manages the AQE representation of broker positions.
    It does not communicate directly with a broker.
    """

    def __init__(
        self,
        repository: PositionRepository,
        account_repository: TradingAccountRepository | None = None,
    ):
        self.repository = repository
        self.account_repository = account_repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_position(
        self,
        data: PositionCreate,
        user_id: UUID | None = None,
        commit: bool = True,
    ):
        """
        Create a new AQE Position.

        A broker position ticket may only correspond to one
        persisted AQE Position.

        New positions are created as OPEN by the Position model's
        default status.
        """

        existing = await self.repository.get_by_ticket(data.ticket)

        if existing:
            raise ValueError("Position with this broker ticket already exists")

        # ------------------------------------------------------
        # Validate order association
        # ------------------------------------------------------

        if data.order_id is None:
            raise ValueError("Position must be associated with an order")

        # ------------------------------------------------------
        # Validate volume relationship
        # ------------------------------------------------------

        if data.current_volume > data.volume:
            raise ValueError("current_volume cannot be greater than volume")

        # ------------------------------------------------------
        # Validate account ownership when requested
        # ------------------------------------------------------

        if user_id is not None and self.account_repository is not None:
            account = await self.account_repository.get_by_id_and_user(
                data.account_id,
                user_id,
            )

            if account is None:
                raise ValueError("Trading account not found")

        # ------------------------------------------------------
        # Persist
        # ------------------------------------------------------

        return await self.repository.create(
            commit=commit,
            **data.model_dump(),
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_position(
        self,
        position_id: UUID,
        user_id: UUID | None = None,
    ):
        """Get a Position by AQE UUID."""

        position = await self.repository.get_by_id(position_id)

        if not position:
            raise ValueError("Position not found")

        if user_id is not None and position.account.user_id != user_id:
            raise ValueError("Position not found")

        return position

    async def get_positions(
        self,
        user_id: UUID | None = None,
    ):
        """Retrieve all positions."""

        positions = await self.repository.get_all()

        if user_id is not None:
            return [
                position
                for position in positions
                if position.account.user_id == user_id
            ]

        return positions

    async def get_open_positions(self):
        """Retrieve all currently open positions."""

        return await self.repository.get_open_positions()

    async def get_account_positions(
        self,
        account_id: UUID,
    ):
        """Retrieve positions belonging to an account."""

        return await self.repository.get_by_account(account_id)

    async def get_symbol_positions(
        self,
        symbol_id: UUID,
    ):
        """Retrieve positions belonging to a symbol."""

        return await self.repository.get_by_symbol(symbol_id)

    async def get_status_positions(
        self,
        position_status: PositionStatus,
    ):
        """Retrieve positions by status."""

        return await self.repository.get_by_status(position_status)

    async def get_position_by_ticket(
        self,
        ticket: int,
    ):
        """Retrieve a position by broker position ticket."""

        position = await self.repository.get_by_ticket(ticket)

        if not position:
            raise ValueError("Position not found")

        return position

    async def get_position_by_order(
        self,
        order_id: UUID,
    ):
        """Retrieve a position by AQE order ID."""

        position = await self.repository.get_by_order(order_id)

        if not position:
            raise ValueError("Position not found")

        return position

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_position(
        self,
        position_id: UUID,
        data: PositionUpdate,
        commit: bool = True,
        user_id: UUID | None = None,
    ):
        """
        Update an existing position.

        OPEN positions may be updated or transitioned to CLOSED.

        CLOSED positions are immutable and cannot be modified.
        """

        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        # ------------------------------------------------------
        # Closed positions are immutable
        # ------------------------------------------------------

        if position.status == PositionStatus.CLOSED:
            raise ValueError("Closed positions cannot be modified")

        update_data = data.model_dump(
            exclude_unset=True,
        )

        # ------------------------------------------------------
        # Validate volume relationship
        # ------------------------------------------------------

        new_volume = update_data.get(
            "volume",
            position.volume,
        )

        new_current_volume = update_data.get(
            "current_volume",
            position.current_volume,
        )

        if new_current_volume > new_volume:
            raise ValueError("current_volume cannot be greater than volume")

        # ------------------------------------------------------
        # Validate status
        # ------------------------------------------------------

        new_status = update_data.get(
            "status",
            position.status,
        )

        if new_status not in {
            PositionStatus.OPEN,
            PositionStatus.CLOSED,
        }:
            raise ValueError(f"Invalid position status: {new_status}")

        # ------------------------------------------------------
        # Closing transition
        # ------------------------------------------------------

        if new_status == PositionStatus.CLOSED:
            # A closed position must have no remaining exposure.
            update_data["current_volume"] = 0

            if "closed_at" not in update_data:
                update_data["closed_at"] = datetime.now(timezone.utc)

        # ------------------------------------------------------
        # OPEN update
        # ------------------------------------------------------

        if new_status == PositionStatus.OPEN:
            update_data.pop("closed_at", None)

        return await self.repository.update(
            position,
            commit=commit,
            **update_data,
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    async def update_position_status(
        self,
        position_id: UUID,
        new_status: PositionStatus,
        commit: bool = True,
        user_id: UUID | None = None,
    ):
        """
        Explicitly transition a position's status.

        Supported lifecycle:

            OPEN -> CLOSED

        A CLOSED position cannot be reopened.
        """

        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        current_status = position.status

        # ------------------------------------------------------
        # Already closed
        # ------------------------------------------------------

        if current_status == PositionStatus.CLOSED:
            if new_status == PositionStatus.CLOSED:
                return position

            raise ValueError("Closed positions cannot be reopened")

        # ------------------------------------------------------
        # OPEN -> OPEN
        # ------------------------------------------------------

        if new_status == PositionStatus.OPEN:
            if current_status != PositionStatus.OPEN:
                raise ValueError(
                    "Position cannot be reopened from its " "current state"
                )

            return position

        # ------------------------------------------------------
        # OPEN -> CLOSED
        # ------------------------------------------------------

        if new_status == PositionStatus.CLOSED:
            position.status = PositionStatus.CLOSED
            position.current_volume = 0

            if position.closed_at is None:
                position.closed_at = datetime.now(timezone.utc)

            return await self.repository.update(
                position,
                commit=commit,
            )

        raise ValueError(f"Unsupported position status: {new_status}")

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_position(
        self,
        position_id: UUID,
        user_id: UUID | None = None,
    ):
        """
        Delete a position.

        Open positions cannot be deleted.
        """

        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        if position.status == PositionStatus.OPEN:
            raise ValueError("Open positions cannot be deleted")

        await self.repository.delete(position)
