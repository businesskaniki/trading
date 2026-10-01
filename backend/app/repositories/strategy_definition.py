"""Repository for StrategyDefinition persistence and catalog lookups."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.strategy_definition import StrategyDefinition


class StrategyDefinitionRepository:
    """
    Repository responsible for StrategyDefinition persistence.

    This repository performs database persistence and catalog lookups
    only.

    It does not decide:

        - whether a strategy should be installed;
        - whether a strategy should be assigned to an account;
        - whether an unavailable strategy may be used;
        - how a Python strategy is discovered;
        - how a strategy is executed.

    Those responsibilities belong to the strategy synchronization and
    service layers.
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
        *,
        commit: bool = True,
        **data,
    ) -> StrategyDefinition:
        """
        Create and persist a StrategyDefinition.

        The caller is responsible for supplying the complete
        synchronized definition data.
        """

        strategy_definition = StrategyDefinition(
            **data,
        )

        self.db.add(
            strategy_definition,
        )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_definition,
        )

        return strategy_definition

    # ==========================================================
    # READ
    # ==========================================================

    async def get_by_id(
        self,
        strategy_definition_id: UUID,
    ) -> StrategyDefinition | None:
        """
        Retrieve a StrategyDefinition by primary key.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            ).where(
                StrategyDefinition.id == strategy_definition_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
    ) -> StrategyDefinition | None:
        """
        Retrieve a StrategyDefinition by canonical strategy name.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            ).where(
                StrategyDefinition.name == name,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_fingerprint(
        self,
        fingerprint: str,
    ) -> StrategyDefinition | None:
        """
        Retrieve a StrategyDefinition by synchronization fingerprint.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            ).where(
                StrategyDefinition.fingerprint == fingerprint,
            )
        )

        return result.scalar_one_or_none()

    async def get_available_by_name(
        self,
        name: str,
    ) -> StrategyDefinition | None:
        """
        Retrieve an available StrategyDefinition by name.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            ).where(
                StrategyDefinition.name == name,
                StrategyDefinition.available.is_(True),
            )
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[StrategyDefinition]:
        """
        Retrieve all StrategyDefinitions.

        Includes both available and retired definitions.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            ).order_by(
                StrategyDefinition.name.asc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_available(
        self,
    ) -> list[StrategyDefinition]:
        """
        Retrieve all currently available StrategyDefinitions.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            )
            .where(
                StrategyDefinition.available.is_(True),
            )
            .order_by(
                StrategyDefinition.name.asc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    async def get_unavailable(
        self,
    ) -> list[StrategyDefinition]:
        """
        Retrieve retired/unavailable StrategyDefinitions.
        """

        result = await self.db.execute(
            select(
                StrategyDefinition,
            )
            .where(
                StrategyDefinition.available.is_(False),
            )
            .order_by(
                StrategyDefinition.name.asc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update(
        self,
        strategy_definition: StrategyDefinition,
        *,
        commit: bool = True,
        **data,
    ) -> StrategyDefinition:
        """
        Update an existing StrategyDefinition.

        Synchronization services are responsible for deciding which
        fields should change.
        """

        for field, value in data.items():
            setattr(
                strategy_definition,
                field,
                value,
            )

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_definition,
        )

        return strategy_definition

    async def set_available(
        self,
        strategy_definition: StrategyDefinition,
        available: bool,
        *,
        commit: bool = True,
    ) -> StrategyDefinition:
        """
        Mark a strategy definition available or retired.
        """

        strategy_definition.available = available

        await self.db.flush()

        if commit:
            await self.db.commit()

        await self.db.refresh(
            strategy_definition,
        )

        return strategy_definition

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        strategy_definition: StrategyDefinition,
        *,
        commit: bool = True,
    ) -> None:
        """
        Delete a StrategyDefinition.

        This should normally NOT be used by synchronization logic.

        Definitions should generally be retired by setting
        ``available=False`` so historical StrategyRuns remain valid.
        """

        await self.db.delete(
            strategy_definition,
        )

        await self.db.flush()

        if commit:
            await self.db.commit()

    # ==========================================================
    # UTILITY
    # ==========================================================

    async def exists_by_name(
        self,
        name: str,
    ) -> bool:
        """
        Return True when a definition with the given name exists.
        """

        return (
            await self.get_by_name(
                name,
            )
        ) is not None

    async def exists_by_fingerprint(
        self,
        fingerprint: str,
    ) -> bool:
        """
        Return True when a definition with the given fingerprint
        exists.
        """

        return (
            await self.get_by_fingerprint(
                fingerprint,
            )
        ) is not None


__all__ = [
    "StrategyDefinitionRepository",
]
