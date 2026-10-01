"""Synchronization of discovered strategies into the AQE database catalog.

The Python strategy registry is the source of truth for which strategy
implementations exist. The database stores a synchronized catalog of those
implementations and account-scoped StrategyRun records.

This module intentionally sits above:

    StrategyDiscovery
        ↓
    StrategyRegistry
        ↓
    StrategySynchronizationService
        ↓
    StrategyDefinitionRepository
    StrategyRunRepository

Discovery remains responsible only for importing/registering strategies.
This service is responsible for synchronizing those registered strategies
with persistent database state.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.models.strategy_definition import (
    StrategyDefinition as StrategyDefinitionModel,
)
from app.database.models.strategy_run import StrategyRun
from app.repositories.strategy_definition import (
    StrategyDefinitionRepository,
)
from app.repositories.strategy_run_repository import StrategyRunRepository

from .core.registry import StrategyRegistry
from .core.registry import registry as default_registry

logger = logging.getLogger(__name__)


class StrategySynchronizationError(RuntimeError):
    """Raised when strategy synchronization cannot be completed."""


class StrategySynchronizationService:
    """
    Synchronize registered Python strategies with persistent AQE state.

    The registry is authoritative for strategy implementation existence.

    The database is a synchronized catalog and account-level configuration
    store. Database records are therefore never used to determine whether
    a Python strategy implementation exists.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: StrategyRegistry | None = None,
        definition_repository: StrategyDefinitionRepository | None = None,
        run_repository: StrategyRunRepository | None = None,
    ) -> None:
        self.db = db

        self.registry = registry or default_registry

        self.definition_repository = (
            definition_repository or StrategyDefinitionRepository(db)
        )

        self.run_repository = run_repository or StrategyRunRepository(db)

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    async def synchronize_definitions(
        self,
        *,
        commit: bool = True,
    ) -> list[StrategyDefinitionModel]:
        """
        Synchronize all registered Python strategies into the database.

        Existing definitions are updated in place.

        New definitions are created.

        Definitions that exist in the database but are no longer present
        in the Python registry are retired by setting ``available=False``.
        They are not deleted because historical StrategyRuns may reference
        them.

        Returns the synchronized database definitions.
        """

        now = datetime.now(timezone.utc)

        registered_definitions = list(
            self.registry.definitions(),
        )

        registered_names: set[str] = set()

        synchronized: list[StrategyDefinitionModel] = []

        for definition in registered_definitions:
            normalized_name = self._normalize_name(
                definition.name,
            )

            registered_names.add(
                normalized_name,
            )

            model = await self._synchronize_definition(
                definition,
                now=now,
                commit=False,
            )

            synchronized.append(
                model,
            )

        await self._retire_missing_definitions(
            registered_names,
            now=now,
            commit=False,
        )

        if commit:
            await self.db.commit()

            for model in synchronized:
                await self.db.refresh(
                    model,
                )

        logger.info(
            "Strategy definition synchronization completed: "
            "%d registered strategies synchronized.",
            len(synchronized),
        )

        return synchronized

    async def synchronize_account(
        self,
        *,
        account_id: UUID,
        user_id: UUID,
        commit: bool = True,
    ) -> list[StrategyRun]:
        """
        Provision missing StrategyRuns for an account.

        Every currently available StrategyDefinition receives at most one
        StrategyRun for the specified account.

        Existing StrategyRuns are preserved and are never duplicated.

        This method does not enable, start, or execute strategies. It only
        ensures that the account has persistent strategy configuration for
        every available strategy implementation.
        """

        definitions = await self.definition_repository.get_available()

        provisioned: list[StrategyRun] = []

        for definition in definitions:
            existing = await self.run_repository.get_by_account_and_definition(
                account_id=account_id,
                strategy_definition_id=definition.id,
                user_id=user_id,
            )

            if existing is not None:
                provisioned.append(
                    existing,
                )
                continue

            strategy_run = await self._create_account_strategy_run(
                account_id=account_id,
                user_id=user_id,
                definition=definition,
                commit=False,
            )

            provisioned.append(
                strategy_run,
            )

        if commit:
            await self.db.commit()

            for strategy_run in provisioned:
                await self.db.refresh(
                    strategy_run,
                )

        logger.info(
            "Strategy run provisioning completed for account %s: "
            "%d strategy runs available.",
            account_id,
            len(provisioned),
        )

        return provisioned

    async def synchronize(
        self,
        *,
        commit: bool = True,
    ) -> list[StrategyDefinitionModel]:
        """
        Synchronize the global strategy catalog.

        This is a convenience alias for ``synchronize_definitions()``.
        """

        return await self.synchronize_definitions(
            commit=commit,
        )

    # ==========================================================
    # STRATEGY DEFINITION SYNCHRONIZATION
    # ==========================================================

    async def _synchronize_definition(
        self,
        definition: Any,
        *,
        now: datetime,
        commit: bool,
    ) -> StrategyDefinitionModel:
        """
        Create or update one StrategyDefinition database record.
        """

        name = self._normalize_name(
            self._required_attribute(
                definition,
                "name",
            ),
        )

        version = str(
            getattr(
                definition,
                "version",
                "1.0.0",
            )
        )

        description = str(
            getattr(
                definition,
                "description",
                "",
            )
            or ""
        )

        author = str(
            getattr(
                definition,
                "author",
                "",
            )
            or ""
        )

        tags = self._normalize_tags(
            getattr(
                definition,
                "tags",
                [],
            )
        )

        strategy_class = self.registry.get(
            name,
        )

        module_path = strategy_class.__module__
        class_name = strategy_class.__name__

        definition_payload = self._serialize_definition(
            definition,
        )

        fingerprint = self._calculate_fingerprint(
            name=name,
            version=version,
            description=description,
            author=author,
            tags=tags,
            module_path=module_path,
            class_name=class_name,
            definition_payload=definition_payload,
        )

        existing = await self.definition_repository.get_by_name(
            name,
        )

        if existing is None:
            model = await self.definition_repository.create(
                commit=False,
                name=name,
                version=version,
                description=description,
                author=author,
                tags=tags,
                module_path=module_path,
                class_name=class_name,
                definition_payload=definition_payload,
                fingerprint=fingerprint,
                available=True,
                first_seen_at=now,
                last_seen_at=now,
            )

            logger.info(
                "Registered new strategy definition '%s' " "(version=%s, class=%s.%s).",
                name,
                version,
                module_path,
                class_name,
            )

            return model

        await self.definition_repository.update(
            existing,
            commit=False,
            version=version,
            description=description,
            author=author,
            tags=tags,
            module_path=module_path,
            class_name=class_name,
            definition_payload=definition_payload,
            fingerprint=fingerprint,
            available=True,
            last_seen_at=now,
        )

        logger.debug(
            "Synchronized strategy definition '%s' " "(version=%s, fingerprint=%s).",
            name,
            version,
            fingerprint,
        )

        return existing

    async def _retire_missing_definitions(
        self,
        registered_names: set[str],
        *,
        now: datetime,
        commit: bool,
    ) -> None:
        """
        Mark database definitions absent from the Python registry unavailable.

        Historical records are retained. We never delete a definition merely
        because its implementation is no longer installed.
        """

        existing_definitions = await self.definition_repository.get_all()

        for definition in existing_definitions:
            normalized_name = self._normalize_name(
                definition.name,
            )

            if normalized_name in registered_names:
                continue

            if not definition.available:
                continue

            await self.definition_repository.update(
                definition,
                commit=False,
                available=False,
                last_seen_at=now,
            )

            logger.warning(
                "Strategy definition '%s' is no longer registered; "
                "marked unavailable.",
                definition.name,
            )

    # ==========================================================
    # ACCOUNT STRATEGY-RUN PROVISIONING
    # ==========================================================

    async def _create_account_strategy_run(
        self,
        *,
        account_id: UUID,
        user_id: UUID,
        definition: StrategyDefinitionModel,
        commit: bool,
    ) -> StrategyRun:
        """
        Create the default persistent StrategyRun for an account.

        The record represents account-level strategy configuration. It is
        initially CREATED and disabled. Actual execution lifecycle is owned
        by the strategy runtime/backtest engine.
        """

        now = datetime.now(timezone.utc)

        run_type = self._default_run_type()

        timeframe = self._default_timeframe(
            definition,
        )

        run_name = self._default_run_name(
            definition.name,
        )

        parameters = self._default_parameters(
            definition,
        )

        symbols = self._default_symbols(
            definition,
        )

        return await self.run_repository.create(
            commit=commit,
            user_id=user_id,
            account_id=account_id,
            strategy_definition_id=definition.id,
            strategy_name=definition.name,
            strategy_version=definition.version,
            run_name=run_name,
            description=definition.description or None,
            enabled=False,
            run_type=run_type,
            status=StrategyRunStatus.CREATED,
            parameters=parameters,
            symbols=symbols,
            timeframe=timeframe,
            started_at=now,
        )

    # ==========================================================
    # DEFAULT STRATEGY CONFIGURATION
    # ==========================================================

    @staticmethod
    def _default_run_type() -> StrategyRunType:
        """
        Return the default persistent account run type.

        StrategyRun represents the account's persistent strategy
        configuration. Backtest composition later creates a BACKTEST
        StrategyConfig from this persisted configuration.

        LIVE is therefore used as the persistent account configuration
        type rather than creating a new StrategyRun for every backtest.
        """

        return StrategyRunType.LIVE

    @staticmethod
    def _default_timeframe(
        definition: StrategyDefinitionModel,
    ) -> str:
        """
        Resolve the strategy's default timeframe.

        A strategy may optionally expose a default timeframe through its
        persisted definition payload. Otherwise M15 is used, matching the
        current AQE historical market-data configuration.
        """

        payload = definition.definition_payload or {}

        timeframe = payload.get(
            "timeframe",
        )

        if timeframe is None:
            timeframe = payload.get(
                "default_timeframe",
            )

        if timeframe is None:
            return "M15"

        return str(
            timeframe,
        )

    @staticmethod
    def _default_parameters(
        definition: StrategyDefinitionModel,
    ) -> dict[str, Any]:
        """
        Extract default strategy parameters from the definition payload.

        The definition payload is treated as immutable strategy metadata.
        A copy is returned so StrategyRun configuration does not share a
        mutable dictionary with the catalog object.
        """

        payload = definition.definition_payload or {}

        parameters = payload.get(
            "parameters",
        )

        if parameters is None:
            parameters = payload.get(
                "default_parameters",
            )

        if not isinstance(
            parameters,
            dict,
        ):
            return {}

        return dict(
            parameters,
        )

    @staticmethod
    def _default_symbols(
        definition: StrategyDefinitionModel,
    ) -> list[str]:
        """
        Return the initial StrategyRun symbol snapshot.

        AccountSymbol is the authoritative trading universe. Therefore the
        synchronization service intentionally does not invent account
        symbols here.

        An optional symbol list contained in the strategy definition is
        retained only as metadata/configuration and may be replaced by the
        account universe during backtest composition.
        """

        payload = definition.definition_payload or {}

        symbols = payload.get(
            "symbols",
        )

        if symbols is None:
            symbols = payload.get(
                "default_symbols",
            )

        if not isinstance(
            symbols,
            (list, tuple),
        ):
            return []

        return [str(symbol).upper() for symbol in symbols if symbol]

    @staticmethod
    def _default_run_name(
        strategy_name: str,
    ) -> str:
        """Build the initial system-generated StrategyRun name."""

        return f"{strategy_name} - Account Strategy"

    # ==========================================================
    # SERIALIZATION
    # ==========================================================

    @staticmethod
    def _serialize_definition(
        definition: Any,
    ) -> dict[str, Any]:
        """
        Convert a Python StrategyDefinition into JSON-compatible data.

        Supports the common AQE definition representations:

            - Pydantic models
            - dataclasses
            - objects exposing model_dump()
            - plain objects exposing __dict__

        The resulting payload is deliberately metadata-oriented. Runtime
        implementation classes are represented separately by module_path
        and class_name.
        """

        if hasattr(
            definition,
            "model_dump",
        ):
            payload = definition.model_dump(
                mode="json",
            )

        elif is_dataclass(
            definition,
        ):
            payload = asdict(
                definition,
            )

        elif hasattr(
            definition,
            "__dict__",
        ):
            payload = dict(
                definition.__dict__,
            )

        else:
            payload = {}

        if not isinstance(
            payload,
            dict,
        ):
            return {}

        return StrategySynchronizationService._json_safe(
            payload,
        )

    @staticmethod
    def _json_safe(
        value: Any,
    ) -> Any:
        """
        Convert common Python values into JSON-compatible structures.
        """

        if value is None:
            return None

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(
            value,
            UUID,
        ):
            return str(
                value,
            )

        if isinstance(
            value,
            datetime,
        ):
            return value.isoformat()

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key): StrategySynchronizationService._json_safe(
                    item,
                )
                for key, item in value.items()
            }

        if isinstance(
            value,
            (list, tuple, set),
        ):
            return [
                StrategySynchronizationService._json_safe(
                    item,
                )
                for item in value
            ]

        if hasattr(
            value,
            "value",
        ):
            return StrategySynchronizationService._json_safe(
                value.value,
            )

        return str(
            value,
        )

    # ==========================================================
    # FINGERPRINTING
    # ==========================================================

    @staticmethod
    def _calculate_fingerprint(
        *,
        name: str,
        version: str,
        description: str,
        author: str,
        tags: list[str],
        module_path: str,
        class_name: str,
        definition_payload: dict[str, Any],
    ) -> str:
        """
        Calculate a deterministic fingerprint for a strategy definition.

        The fingerprint changes whenever the persisted definition metadata
        or implementation identity changes.
        """

        fingerprint_payload = {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
            "tags": sorted(tags),
            "module_path": module_path,
            "class_name": class_name,
            "definition_payload": definition_payload,
        }

        serialized = json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        )

        return hashlib.sha256(
            serialized.encode(
                "utf-8",
            ),
        ).hexdigest()

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_name(
        value: Any,
    ) -> str:
        """Normalize a strategy name for database identity lookups."""

        normalized = (
            str(
                value,
            )
            .strip()
            .lower()
        )

        if not normalized:
            raise StrategySynchronizationError(
                "Strategy definition name cannot be empty.",
            )

        return normalized

    @staticmethod
    def _normalize_tags(
        value: Any,
    ) -> list[str]:
        """Normalize strategy tags into a unique sorted list."""

        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            values = [
                value,
            ]
        elif isinstance(
            value,
            (list, tuple, set),
        ):
            values = list(
                value,
            )
        else:
            values = []

        normalized = {str(tag).strip().lower() for tag in values if str(tag).strip()}

        return sorted(
            normalized,
        )

    @staticmethod
    def _required_attribute(
        obj: Any,
        attribute: str,
    ) -> Any:
        """
        Retrieve a required strategy-definition attribute.
        """

        value = getattr(
            obj,
            attribute,
            None,
        )

        if value is None:
            raise StrategySynchronizationError(
                f"Strategy definition is missing required " f"attribute '{attribute}'.",
            )

        return value


__all__ = [
    "StrategySynchronizationError",
    "StrategySynchronizationService",
]
