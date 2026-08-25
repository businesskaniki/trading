from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.core.constants import PositionStatus
from app.repositories.position_repository import PositionRepository
from app.schemas.position import PositionCreate, PositionUpdate


class PositionService:
    """
    Business logic layer for Positions.

    This service manages the AQE representation of broker positions.
    It does not communicate directly with MT5.
    """

    def __init__(
        self,
        repository: PositionRepository,
    ):
        self.repository = repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_position(
        self,
        data: PositionCreate,
    ):
        """
        Create a new AQE Position.

        A broker ticket may only correspond to one persisted
        Position record.
        """

        existing = await self.repository.get_by_ticket(
            data.ticket
        )

        if existing:
            raise ValueError(
                "Position with this broker ticket already exists"
            )

        # ------------------------------------------------------
        # Validate volume relationship
        # ------------------------------------------------------

        if data.current_volume > data.volume:
            raise ValueError(
                "current_volume cannot be greater than volume"
            )

        # ------------------------------------------------------
        # New positions must be OPEN
        # ------------------------------------------------------

        if data.order_id is None:
            raise ValueError(
                "Position must be associated with an order"
            )

        return await self.repository.create(
            **data.model_dump()
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_position(
        self,
        position_id: UUID,
    ):
        """
        Get a Position by AQE UUID.
        """

        position = await self.repository.get_by_id(
            position_id
        )

        if not position:
            raise ValueError(
                "Position not found"
            )

        return position

    # ----------------------------------------------------------
    # ALL POSITIONS
    # ----------------------------------------------------------

    async def get_positions(self):

        return await self.repository.get_all()

    # ----------------------------------------------------------
    # OPEN POSITIONS
    # ----------------------------------------------------------

    async def get_open_positions(self):

        return await self.repository.get_open_positions()

    # ----------------------------------------------------------
    # ACCOUNT POSITIONS
    # ----------------------------------------------------------

    async def get_account_positions(
        self,
        account_id: UUID,
    ):

        return await self.repository.get_by_account(
            account_id
        )

    # ----------------------------------------------------------
    # SYMBOL POSITIONS
    # ----------------------------------------------------------

    async def get_symbol_positions(
        self,
        symbol_id: UUID,
    ):

        return await self.repository.get_by_symbol(
            symbol_id
        )

    # ----------------------------------------------------------
    # STATUS POSITIONS
    # ----------------------------------------------------------

    async def get_status_positions(
        self,
        position_status: PositionStatus,
    ):

        return await self.repository.get_by_status(
            position_status
        )

    # ----------------------------------------------------------
    # BY BROKER TICKET
    # ----------------------------------------------------------

    async def get_position_by_ticket(
        self,
        ticket: int,
    ):

        position = await self.repository.get_by_ticket(
            ticket
        )

        if not position:
            raise ValueError(
                "Position not found"
            )

        return position

    # ----------------------------------------------------------
    # BY ORDER
    # ----------------------------------------------------------

    async def get_position_by_order(
        self,
        order_id: UUID,
    ):

        position = await self.repository.get_by_order(
            order_id
        )

        if not position:
            raise ValueError(
                "Position not found"
            )

        return position

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_position(
        self,
        position_id: UUID,
        data: PositionUpdate,
        commit: bool = True,
    ):

        position = await self.get_position(
            position_id
        )

        # ------------------------------------------------------
        # Closed positions
        # ------------------------------------------------------

        if position.status == PositionStatus.CLOSED:
            raise ValueError(
                "Closed positions cannot be modified"
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        # ------------------------------------------------------
        # Validate current volume
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
            raise ValueError(
                "current_volume cannot be greater than volume"
            )

        # ------------------------------------------------------
        # Status transition validation
        # ------------------------------------------------------

        new_status = update_data.get(
            "status",
            position.status,
        )

        if (
            position.status == PositionStatus.CLOSED
            and new_status != PositionStatus.CLOSED
        ):
            raise ValueError(
                "Closed positions cannot be reopened"
            )

        # ------------------------------------------------------
        # Closing timestamp
        # ------------------------------------------------------

        if new_status == PositionStatus.CLOSED:

            if "closed_at" not in update_data:
                update_data["closed_at"] = datetime.now(
                    timezone.utc
                )

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
    ):
        position = await self.get_position(
            position_id
        )

        current_status = position.status

        if current_status == PositionStatus.CLOSED:
            if new_status == PositionStatus.CLOSED:
                return position

            raise ValueError(
                "Closed positions cannot be reopened"
            )

        if new_status == PositionStatus.OPEN:
            if current_status != PositionStatus.OPEN:
                raise ValueError(
                    "Position cannot be reopened from its current state"
                )

        if new_status == PositionStatus.CLOSED:
            position.status = PositionStatus.CLOSED

            if position.closed_at is None:
                position.closed_at = datetime.now(
                    timezone.utc
                )

            return await self.repository.update(
                position,
                commit=commit,
            )

        return await self.repository.update_status(
            position,
            new_status,
            commit=commit,
        )

    
    # DELETE
    # ==========================================================

    async def delete_position(
        self,
        position_id: UUID,
    ):

        position = await self.get_position(
            position_id
        )

        if position.status == PositionStatus.OPEN:
            raise ValueError(
                "Open positions cannot be deleted"
            )

        await self.repository.delete(
            position
        )