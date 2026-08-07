from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.password_reset import PasswordReset


class PasswordResetRepository:
    """
    Repository for PasswordReset operations.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        password_reset: PasswordReset,
    ) -> PasswordReset:
        self.session.add(password_reset)
        await self.session.commit()
        await self.session.refresh(password_reset)
        return password_reset

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        reset_id: UUID,
    ) -> PasswordReset | None:
        result = await self.session.execute(
            select(PasswordReset).where(
                PasswordReset.id == reset_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> PasswordReset | None:
        result = await self.session.execute(
            select(PasswordReset).where(
                PasswordReset.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_user_id(
        self,
        user_id: UUID,
    ) -> PasswordReset | None:
        result = await self.session.execute(
            select(PasswordReset).where(
                PasswordReset.user_id == user_id,
                PasswordReset.used.is_(False),
            )
        )
        return result.scalar_one_or_none()

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        password_reset: PasswordReset,
    ) -> PasswordReset:
        await self.session.commit()
        await self.session.refresh(password_reset)
        return password_reset

    async def mark_used(
        self,
        password_reset: PasswordReset,
    ) -> PasswordReset:
        password_reset.used = True

        await self.session.commit()
        await self.session.refresh(password_reset)

        return password_reset

    async def increment_attempts(
        self,
        password_reset: PasswordReset,
    ) -> PasswordReset:
        password_reset.attempts += 1

        await self.session.commit()
        await self.session.refresh(password_reset)

        return password_reset

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        password_reset: PasswordReset,
    ) -> None:
        await self.session.delete(password_reset)
        await self.session.commit()

    async def delete_by_user_id(
        self,
        user_id: UUID,
    ) -> None:
        password_reset = await self.get_by_user_id(user_id)

        if password_reset:
            await self.session.delete(password_reset)
            await self.session.commit()