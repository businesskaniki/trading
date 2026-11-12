from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.constants import PositionStatus
from app.repositories.position_repository import PositionRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.position import PositionCreate, PositionUpdate


class PositionService:
    """
    Business logic for AQE's persisted representation of broker positions.

    The service does not communicate directly with a broker.
    """

    def __init__(
        self,
        repository: PositionRepository,
        account_repository: TradingAccountRepository | None = None,
    ) -> None:
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
        Persist an open position.

        order_id is optional because a broker may contain a position
        opened manually or by an external trading system.
        """

        existing = await self.repository.get_by_ticket(data.ticket)

        if existing is not None:
            raise ValueError("Position with this broker ticket already exists")

        current_volume = (
            data.volume if data.current_volume is None else data.current_volume
        )

        if current_volume < 0:
            raise ValueError("current_volume cannot be negative")

        if current_volume > data.volume:
            raise ValueError("current_volume cannot be greater than volume")

        if user_id is not None and self.account_repository is not None:
            account = await self.account_repository.get_by_id_and_user(
                data.account_id,
                user_id,
            )

            if account is None:
                raise ValueError("Trading account not found")

        payload = data.model_dump()
        payload["current_volume"] = current_volume

        return await self.repository.create(
            commit=commit,
            **payload,
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_position(
        self,
        position_id: UUID,
        user_id: UUID | None = None,
    ):
        position = await self.repository.get_by_id(position_id)

        if position is None:
            raise ValueError("Position not found")

        if user_id is not None and position.account.user_id != user_id:
            raise ValueError("Position not found")

        return position

    async def get_positions(
        self,
        user_id: UUID | None = None,
    ):
        positions = await self.repository.get_all()

        if user_id is None:
            return positions

        return [
            position for position in positions if position.account.user_id == user_id
        ]

    
    async def get_open_positions_for_user(
        self,
        user_id: UUID,
        account_id: UUID | None = None,
    ):
        """Return only open positions owned by this user.

        When account_id is supplied, restrict results to that account.
        Closed positions remain available through get_positions().
        """
        if account_id is not None:
            positions = (
                await self.repository.get_open_positions_by_account(
                    account_id
                )
            )
        else:
            positions = await self.repository.get_open_positions()

        return [
            position
            for position in positions
            if position.account is not None
            and position.account.user_id == user_id
        ]


    async def get_open_positions(self):
        return await self.repository.get_open_positions()

    async def get_account_positions(self, account_id: UUID):
        return await self.repository.get_by_account(account_id)

    async def get_symbol_positions(self, symbol_id: UUID):
        return await self.repository.get_by_symbol(symbol_id)

    async def get_status_positions(self, position_status: PositionStatus):
        return await self.repository.get_by_status(position_status)

    async def get_position_by_ticket(self, ticket: int):
        position = await self.repository.get_by_ticket(ticket)

        if position is None:
            raise ValueError("Position not found")

        return position

    async def get_position_by_order(self, order_id: UUID):
        position = await self.repository.get_by_order(order_id)

        if position is None:
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
        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        if position.status == PositionStatus.CLOSED:
            raise ValueError("Closed positions cannot be modified")

        update_data = data.model_dump(exclude_unset=True)

        new_volume = update_data.get("volume", position.volume)
        new_current_volume = update_data.get(
            "current_volume",
            position.current_volume,
        )

        if new_current_volume is None:
            new_current_volume = position.current_volume

        if new_current_volume < 0:
            raise ValueError("current_volume cannot be negative")

        if new_current_volume > new_volume:
            raise ValueError("current_volume cannot be greater than volume")

        new_status = update_data.get("status", position.status)

        if new_status not in {
            PositionStatus.OPEN,
            PositionStatus.CLOSED,
        }:
            raise ValueError(f"Invalid position status: {new_status}")

        if new_status == PositionStatus.CLOSED:
            update_data["current_volume"] = 0

            if update_data.get("closed_at") is None:
                update_data["closed_at"] = datetime.now(timezone.utc)

        elif new_status == PositionStatus.OPEN:
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
        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        if position.status == PositionStatus.CLOSED:
            if new_status == PositionStatus.CLOSED:
                return position

            raise ValueError("Closed positions cannot be reopened")

        if new_status == PositionStatus.OPEN:
            if position.status != PositionStatus.OPEN:
                raise ValueError("Position cannot be reopened from its current state")

            return position

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
    ) -> None:
        position = await self.get_position(
            position_id,
            user_id=user_id,
        )

        if position.status == PositionStatus.OPEN:
            raise ValueError("Open positions cannot be deleted")

        await self.repository.delete(position)
