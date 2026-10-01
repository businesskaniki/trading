"""Synchronization of the AQE strategy registry with the database catalog."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.strategy_definition import StrategyDefinition
from strategies.bootstrap import strategy_bootstrap
from strategies.core.base import StrategyDefinition as StrategyDefinitionContract
from strategies.core.registry import StrategyRegistry
from strategies.core.registry import registry as strategy_registry

logger = logging.getLogger(__name__)


class StrategyDefinitionSyncError(RuntimeError):
    """Raised when strategy-definition synchronization fails."""


class StrategyDefinitionSyncService:
    """
    Synchronize registered AQE strategy implementations with PostgreSQL.

    The Python strategy registry remains the source of truth for which
    implementations currently exist.

    The database table ``strategy_definitions`` is a persistent catalog
    used by application APIs, account configuration, runtime validation,
    and historical references.

    Synchronization rules
    ---------------------
    Registered strategy:
        - insert when missing
        - update metadata when the definition changed
        - set ``available=True``
        - refresh ``last_seen_at``

    Previously registered strategy that is no longer discovered:
        - retain the database row
        - set ``available=False``
        - do not delete it

    Transaction ownership
    ---------------------
    The service does not commit or rollback the database transaction.
    The caller owns the transaction boundary.

    This makes the service safe to use during application startup,
    background jobs, API operations, and tests.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        registry: StrategyRegistry | None = None,
    ) -> None:
        """
        Initialize the synchronization service.

        Args:
            session:
                SQLAlchemy async session used for catalog synchronization.

            registry:
                Strategy registry to synchronize.

                Defaults to the application's global AQE strategy registry.
        """

        if not isinstance(session, AsyncSession):
            raise TypeError("session must be an instance of AsyncSession.")

        self._session = session
        self._registry = strategy_registry if registry is None else registry

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    async def sync(
        self,
    ) -> tuple[StrategyDefinition, ...]:
        """
        Synchronize the database catalog with discovered strategies.

        The existing AQE StrategyBootstrap is started before the registry
        is inspected. Therefore this method can safely be called during
        application startup without requiring the caller to separately
        discover strategy modules first.

        Returns:
            Database StrategyDefinition objects representing the
            currently registered strategy implementations.

        Raises:
            StrategyDefinitionSyncError:
                If synchronization cannot be completed.
        """

        try:
            await strategy_bootstrap.start()

            registered = self._collect_registered_strategies()

            existing_rows = await self._load_existing_definitions()

            now = datetime.now(timezone.utc)

            synchronized_rows: list[StrategyDefinition] = []

            for registration_name, strategy_class in registered.items():
                definition = strategy_class.definition

                row = existing_rows.get(definition.name.strip().lower())

                if row is None:
                    row = self._create_definition_row(
                        definition=definition,
                        strategy_class=strategy_class,
                        now=now,
                    )

                    self._session.add(row)

                    synchronized_rows.append(row)

                    logger.info(
                        "Registered new strategy definition in database: "
                        "name=%s version=%s implementation=%s.%s",
                        definition.name,
                        definition.version,
                        strategy_class.__module__,
                        strategy_class.__qualname__,
                    )

                    continue

                self._update_definition_row(
                    row=row,
                    definition=definition,
                    strategy_class=strategy_class,
                    now=now,
                )

                synchronized_rows.append(row)

            self._retire_missing_definitions(
                existing_rows=existing_rows,
                registered_names={
                    definition.name.strip().lower()
                    for definition in (
                        strategy_class.definition
                        for strategy_class in registered.values()
                    )
                },
            )

            await self._session.flush()

            logger.info(
                "Strategy definition catalog synchronized: "
                "registered=%d existing=%d",
                len(registered),
                len(existing_rows),
            )

            return tuple(synchronized_rows)

        except StrategyDefinitionSyncError:
            raise

        except Exception as exc:
            logger.exception("Strategy definition catalog synchronization failed.")

            raise StrategyDefinitionSyncError(
                "Failed to synchronize the strategy definition catalog."
            ) from exc

    async def sync_and_return(
        self,
    ) -> list[StrategyDefinition]:
        """
        Synchronize the catalog and return the resulting rows as a list.

        This convenience method is useful for application bootstrap and
        administrative services that need a mutable collection.
        """

        rows = await self.sync()

        return list(rows)

    # ==================================================================
    # DISCOVERY / REGISTRY
    # ==================================================================

    def _collect_registered_strategies(
        self,
    ) -> dict[str, type[Any]]:
        """
        Return the currently registered strategy classes.

        ``StrategyBootstrap`` has already populated the registry before
        this method is called.

        The registry itself remains the authoritative runtime discovery
        source.
        """

        registered = self._registry.all()

        if not registered:
            logger.warning("Strategy registry is empty after bootstrap.")

        return registered

    # ==================================================================
    # DATABASE ACCESS
    # ==================================================================

    async def _load_existing_definitions(
        self,
    ) -> dict[str, StrategyDefinition]:
        """
        Load all strategy-definition catalog rows indexed by normalized name.
        """

        result = await self._session.execute(select(StrategyDefinition))

        rows = result.scalars().all()

        return {row.name.strip().lower(): row for row in rows}

    # ==================================================================
    # CREATE
    # ==================================================================

    @classmethod
    def _create_definition_row(
        cls,
        *,
        definition: StrategyDefinitionContract,
        strategy_class: type[Any],
        now: datetime,
    ) -> StrategyDefinition:
        """
        Create a new database catalog row from a strategy implementation.
        """

        payload = cls._build_definition_payload(
            definition=definition,
            strategy_class=strategy_class,
        )

        fingerprint = cls._fingerprint(
            payload,
        )

        return StrategyDefinition(
            name=definition.name.strip(),
            version=definition.version.strip(),
            description=definition.description.strip(),
            author=definition.author.strip(),
            tags=list(definition.tags),
            module_path=strategy_class.__module__,
            class_name=strategy_class.__qualname__,
            definition_payload=payload,
            fingerprint=fingerprint,
            available=True,
            first_seen_at=now,
            last_seen_at=now,
        )

    # ==================================================================
    # UPDATE
    # ==================================================================

    @classmethod
    def _update_definition_row(
        cls,
        *,
        row: StrategyDefinition,
        definition: StrategyDefinitionContract,
        strategy_class: type[Any],
        now: datetime,
    ) -> None:
        """
        Update an existing catalog row.

        The row retains its original primary key and ``first_seen_at``.
        """

        payload = cls._build_definition_payload(
            definition=definition,
            strategy_class=strategy_class,
        )

        fingerprint = cls._fingerprint(
            payload,
        )

        changed = row.fingerprint != fingerprint

        if changed:
            logger.info(
                "Strategy definition changed: " "name=%s old_version=%s new_version=%s",
                row.name,
                row.version,
                definition.version,
            )

        row.name = definition.name.strip()
        row.version = definition.version.strip()
        row.description = definition.description.strip()
        row.author = definition.author.strip()
        row.tags = list(definition.tags)
        row.module_path = strategy_class.__module__
        row.class_name = strategy_class.__qualname__
        row.definition_payload = payload
        row.fingerprint = fingerprint
        row.available = True
        row.last_seen_at = now

    # ==================================================================
    # RETIREMENT
    # ==================================================================

    @staticmethod
    def _retire_missing_definitions(
        *,
        existing_rows: Mapping[str, StrategyDefinition],
        registered_names: set[str],
    ) -> None:
        """
        Mark catalog entries absent from the current registry unavailable.

        Rows are never physically deleted.
        """

        for normalized_name, row in existing_rows.items():
            if normalized_name in registered_names:
                continue

            if row.available:
                row.available = False

                logger.warning(
                    "Strategy definition is no longer registered and "
                    "has been marked unavailable: name=%s version=%s",
                    row.name,
                    row.version,
                )

    # ==================================================================
    # PAYLOAD / FINGERPRINT
    # ==================================================================

    @staticmethod
    def _build_definition_payload(
        *,
        definition: StrategyDefinitionContract,
        strategy_class: type[Any],
    ) -> dict[str, Any]:
        """
        Build the canonical JSON-serializable definition snapshot.

        The payload contains both static strategy metadata and the
        concrete implementation identity.
        """

        return {
            "name": definition.name.strip(),
            "version": definition.version.strip(),
            "description": definition.description.strip(),
            "author": definition.author.strip(),
            "tags": sorted(
                {str(tag).strip() for tag in definition.tags if str(tag).strip()}
            ),
            "module_path": strategy_class.__module__,
            "class_name": strategy_class.__qualname__,
        }

    @staticmethod
    def _fingerprint(
        payload: Mapping[str, Any],
    ) -> str:
        """
        Return a deterministic SHA-256 fingerprint for a definition payload.
        """

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

        return hashlib.sha256(
            canonical.encode("utf-8"),
        ).hexdigest()


# ======================================================================
# FACTORY
# ======================================================================


def get_strategy_definition_sync_service(
    session: AsyncSession,
) -> StrategyDefinitionSyncService:
    """
    Construct a strategy-definition synchronization service.
    """

    return StrategyDefinitionSyncService(
        session=session,
    )
