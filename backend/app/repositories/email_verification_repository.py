from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.email_verification import EmailVerification


class EmailVerificationRepository:
    """
    Repository for EmailVerification operations.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        verification: EmailVerification,
    ) -> EmailVerification:
        self.session.add(verification)
        await self.session.commit()
        await self.session.refresh(verification)
        return verification

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        verification_id: UUID,
    ) -> EmailVerification | None:
        result = await self.session.execute(
            select(EmailVerification).where(
                EmailVerification.id == verification_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> EmailVerification | None:
        result = await self.session.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_user_id(
        self,
        user_id: UUID,
    ) -> EmailVerification | None:
        result = await self.session.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user_id,
                EmailVerification.verified.is_(False),
            )
        )
        return result.scalar_one_or_none()

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        verification: EmailVerification,
    ) -> EmailVerification:
        await self.session.commit()
        await self.session.refresh(verification)
        return verification

    async def mark_verified(
        self,
        verification: EmailVerification,
    ) -> EmailVerification:
        verification.verified = True

        await self.session.commit()
        await self.session.refresh(verification)

        return verification

    async def increment_attempts(
        self,
        verification: EmailVerification,
    ) -> EmailVerification:
        verification.attempts += 1

        await self.session.commit()
        await self.session.refresh(verification)

        return verification

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        verification: EmailVerification,
    ) -> None:
        await self.session.delete(verification)
        await self.session.commit()

    async def delete_by_user_id(
        self,
        user_id: UUID,
    ) -> None:
        verification = await self.get_by_user_id(user_id)

        if verification:
            await self.session.delete(verification)
            await self.session.commit()