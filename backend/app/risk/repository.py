from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.risk.models import RiskProfile


class RiskProfileRepository:
    """
    Persistence operations for RiskProfile.
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
    ) -> RiskProfile:

        profile = RiskProfile(
            **data
        )

        self.db.add(profile)

        await self.db.commit()

        await self.db.refresh(
            profile
        )

        return profile

    # ==========================================================
    # GET BY ACCOUNT
    # ==========================================================

    async def get_by_account(
        self,
        account_id: UUID,
    ) -> RiskProfile | None:

        result = await self.db.execute(
            select(RiskProfile)
            .where(
                RiskProfile.account_id == account_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # GET BY ID
    # ==========================================================

    async def get_by_id(
        self,
        profile_id: UUID,
    ) -> RiskProfile | None:

        result = await self.db.execute(
            select(RiskProfile)
            .where(
                RiskProfile.id == profile_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update(
        self,
        profile: RiskProfile,
        **data,
    ) -> RiskProfile:

        for field, value in data.items():
            setattr(
                profile,
                field,
                value,
            )

        await self.db.commit()

        await self.db.refresh(
            profile
        )

        return profile