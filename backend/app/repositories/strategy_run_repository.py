"""Repository for StrategyRun persistence and account-scoped lookups."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.models.strategy_run import StrategyRun


class StrategyRunRepository:
    """
    Repository responsible for StrategyRun database operations.

    This repository performs persistence and database lookups only.

    Business rules such as:

        - whether a StrategyDefinition is assignable;
        - whether a user owns an account;
        - whether a StrategyRun may change identity;

    belong to the service layer.

    StrategyDefinition persistence is handled separately by
    StrategyDefinitionRepository.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """Initialize the repository."""

        self.db = db

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create(
        self,
        commit: bool = True,
        **data,
    ) -> StrategyRun:
        """
        Create and persist a StrategyRun.

        The service layer supplies the StrategyRun identity,
        configuration, and strategy_definition_id.
        """

        strategy_run = StrategyRun(
            **data,
        )

        self.db.add(
            strategy_run,
        )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_run,
        )

        return strategy_run

    # ==========================================================
    # READ
    # ==========================================================

    async def get_by_id(
        self,
        strategy_run_id: UUID,
        user_id: UUID | None = None,
    ) -> StrategyRun | None:
        """
        Retrieve a StrategyRun by ID.

        When user_id is supplied, the lookup is restricted to that
        user's StrategyRuns.
        """

        query = select(
            StrategyRun,
        ).where(
            StrategyRun.id == strategy_run_id,
        )

        if user_id is not None:
            query = query.where(
                StrategyRun.user_id == user_id,
            )

        result = await self.db.execute(
            query,
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        strategy_name: str,
    ) -> list[StrategyRun]:
        """
        Retrieve all StrategyRuns with the given strategy-name
        snapshot.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.strategy_name == strategy_name,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_status(
        self,
        status: StrategyRunStatus,
    ) -> list[StrategyRun]:
        """
        Retrieve all StrategyRuns with the given status.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.status == status,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_type(
        self,
        run_type: StrategyRunType,
    ) -> list[StrategyRun]:
        """
        Retrieve all StrategyRuns with the given run type.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.run_type == run_type,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_account(
        self,
        account_id: UUID,
        user_id: UUID | None = None,
    ) -> list[StrategyRun]:
        """
        Retrieve all StrategyRuns associated with an account.

        When user_id is supplied, the result is additionally restricted
        to StrategyRuns owned by that user.
        """

        query = (
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.account_id == account_id,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        if user_id is not None:
            query = query.where(
                StrategyRun.user_id == user_id,
            )

        result = await self.db.execute(
            query,
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_account_and_definition(
        self,
        account_id: UUID,
        strategy_definition_id: UUID,
        user_id: UUID | None = None,
    ) -> StrategyRun | None:
        """
        Retrieve the StrategyRun assigned to an account for a
        specific StrategyDefinition.

        This lookup is used by automatic strategy provisioning to
        make account-level StrategyRun creation idempotent.

        When user_id is supplied, the lookup is additionally restricted
        to that user.
        """

        query = (
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.account_id == account_id,
                StrategyRun.strategy_definition_id == strategy_definition_id,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
            .limit(1)
        )

        if user_id is not None:
            query = query.where(
                StrategyRun.user_id == user_id,
            )

        result = await self.db.execute(
            query,
        )

        return result.scalar_one_or_none()

    async def get_enabled_for_account(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> list[StrategyRun]:
        """
        Retrieve enabled StrategyRuns configured for an account.

        The lookup is scoped to both account_id and user_id so callers
        cannot accidentally load another user's strategy
        configuration.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.account_id == account_id,
                StrategyRun.user_id == user_id,
                StrategyRun.enabled.is_(True),
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_strategy_definition(
        self,
        strategy_definition_id: UUID,
        user_id: UUID | None = None,
    ) -> list[StrategyRun]:
        """
        Retrieve StrategyRuns referencing a StrategyDefinition.

        When user_id is supplied, only that user's StrategyRuns are
        returned.
        """

        query = (
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.strategy_definition_id == strategy_definition_id,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
        )

        if user_id is not None:
            query = query.where(
                StrategyRun.user_id == user_id,
            )

        result = await self.db.execute(
            query,
        )

        return list(
            result.scalars().all(),
        )

    async def get_latest(
        self,
    ) -> StrategyRun | None:
        """
        Retrieve the most recently started StrategyRun.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_latest_for_user(
        self,
        user_id: UUID,
    ) -> StrategyRun | None:
        """
        Retrieve the most recently started StrategyRun for a user.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.user_id == user_id,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_running_for_user(
        self,
        user_id: UUID,
    ) -> StrategyRun | None:
        """
        Retrieve the most recently started running StrategyRun for a
        user.
        """

        result = await self.db.execute(
            select(
                StrategyRun,
            )
            .where(
                StrategyRun.user_id == user_id,
                StrategyRun.status == StrategyRunStatus.RUNNING,
            )
            .order_by(
                StrategyRun.started_at.desc(),
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
        user_id: UUID | None = None,
    ) -> list[StrategyRun]:
        """
        Retrieve all StrategyRuns.

        When user_id is supplied, only that user's runs are returned.
        """

        query = select(
            StrategyRun,
        )

        if user_id is not None:
            query = query.where(
                StrategyRun.user_id == user_id,
            )

        query = query.order_by(
            StrategyRun.started_at.desc(),
        )

        result = await self.db.execute(
            query,
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update(
        self,
        strategy_run: StrategyRun,
        commit: bool = True,
        **data,
    ) -> StrategyRun:
        """
        Update an existing StrategyRun.

        The service layer is responsible for preventing updates to
        immutable identity fields.
        """

        for field, value in data.items():
            setattr(
                strategy_run,
                field,
                value,
            )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_run,
        )

        return strategy_run

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        strategy_run: StrategyRun,
        commit: bool = True,
    ) -> None:
        """
        Delete an existing StrategyRun.
        """

        await self.db.delete(
            strategy_run,
        )

        await self.db.flush()

        if commit:
            await self.db.commit()

    # ==========================================================
    # UTILITY
    # ==========================================================

    async def exists(
        self,
        strategy_run_id: UUID,
    ) -> bool:
        """
        Return True when a StrategyRun exists.
        """

        return (
            await self.get_by_id(
                strategy_run_id,
            )
        ) is not None


__all__ = [
    "StrategyRunRepository",
]