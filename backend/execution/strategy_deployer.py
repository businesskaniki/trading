"""Deploy persisted StrategyRun records into the live strategy runtime.

This module is the application-layer bridge between persistent strategy
configuration and the in-memory StrategyManager.

Responsibilities:

    StrategyRun
        -> validate account ownership
        -> validate StrategyDefinition
        -> validate installed implementation
        -> resolve enabled account symbols
        -> build StrategyConfig
        -> StrategyManager.create()
        -> activate()
        -> start()

Runtime symbol ownership is intentionally account-level:

    TradingAccount
        -> AccountSymbol.enabled
        -> canonical AQE symbols
        -> StrategyConfig.symbols

StrategyRun.symbols remains a persisted configuration/history snapshot. It is
not authoritative for the live runtime symbol universe.

This module deliberately does not:

    - generate trading signals
    - evaluate risk
    - execute orders
    - communicate with brokers
    - communicate with MT5
    - publish market-data events
    - manage engine lifecycle

Database session ownership also belongs here. The engine should not need to
know how StrategyRun or AccountSymbol persistence is implemented.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.models.strategy_definition import StrategyDefinition
from app.database.models.strategy_run import StrategyRun
from app.database.session import SessionLocal
from app.repositories.strategy_run_repository import StrategyRunRepository
from strategies.core import StrategyConfig
from strategies.core import StrategyMode
from strategies.core.registry import StrategyRegistry
from strategies.core.registry import registry as strategy_registry
from strategies.runtime.manager import StrategyManager

from .account_symbol_resolver import (
    AccountSymbolResolutionError,
    AccountSymbolResolver,
)

logger = logging.getLogger(__name__)


class StrategyDeploymentError(RuntimeError):
    """Raised when a persisted strategy cannot be deployed."""


@dataclass(frozen=True, slots=True)
class StrategyDeploymentResult:
    """Result of deploying persisted strategies for one account."""

    account_id: UUID
    deployed_strategy_ids: tuple[str, ...]
    skipped_strategy_ids: tuple[str, ...]
    failed_strategy_ids: tuple[str, ...]

    @property
    def deployed_count(self) -> int:
        """Return the number of successfully deployed strategies."""

        return len(self.deployed_strategy_ids)

    @property
    def skipped_count(self) -> int:
        """Return the number of strategies skipped during deployment."""

        return len(self.skipped_strategy_ids)

    @property
    def failed_count(self) -> int:
        """Return the number of strategies that failed deployment."""

        return len(self.failed_strategy_ids)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable deployment summary."""

        return {
            "account_id": str(self.account_id),
            "deployed_strategy_ids": list(
                self.deployed_strategy_ids,
            ),
            "skipped_strategy_ids": list(
                self.skipped_strategy_ids,
            ),
            "failed_strategy_ids": list(
                self.failed_strategy_ids,
            ),
            "deployed_count": self.deployed_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
        }


class LiveStrategyDeployer:
    """
    Deploy persisted LIVE/PAPER StrategyRun records into a runtime.

    A StrategyRun is deployable when:

    - it belongs to the requested user;
    - it is enabled;
    - its status is RUNNING;
    - its run type is LIVE or PAPER;
    - its account_id is present;
    - its account_id matches the active runtime account;
    - it references an available StrategyDefinition;
    - the StrategyDefinition matches the currently registered
      implementation;
    - the account has an enabled AccountSymbol universe;
    - its runtime configuration is valid.

    The StrategyRun UUID becomes the runtime ``strategy_id``.

    StrategyDefinition is the persistent catalog identity of the
    installed strategy implementation.

    StrategyRun.strategy_name and StrategyRun.strategy_version remain
    historical/configuration snapshots, but active deployment requires
    them to agree with the referenced StrategyDefinition.

    StrategyRun.symbols is deliberately not used as the runtime
    universe. Every eligible StrategyRun for an account receives all
    enabled canonical symbols resolved by AccountSymbolResolver.

    Database session ownership belongs to this deployer.
    """

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        registry: StrategyRegistry | None = None,
    ) -> None:
        """Initialize the strategy deployer."""

        self.session_factory = session_factory
        self.registry = strategy_registry if registry is None else registry

    # ==================================================================
    # DEPLOYMENT
    # ==================================================================

    async def deploy_for_account(
        self,
        *,
        account_id: UUID,
        user_id: UUID,
        strategy_manager: StrategyManager,
    ) -> StrategyDeploymentResult:
        """
        Deploy all eligible persisted strategies for one account.

        Only StrategyRun records belonging to ``user_id`` are
        considered.

        Deployment requires StrategyRun.account_id to match the
        account currently owned by the runtime.

        The database StrategyDefinition must resolve to an
        available, currently registered implementation.

        Runtime symbols are resolved once from the account's enabled
        AccountSymbol records and shared by every deployed strategy
        for that account.
        """

        self._validate_inputs(
            account_id=account_id,
            user_id=user_id,
            strategy_manager=strategy_manager,
        )

        deployed: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        async with self.session_factory() as session:
            repository = StrategyRunRepository(
                session,
            )

            runs = await repository.get_all(
                user_id=user_id,
            )

            candidate_runs = [run for run in runs if self._is_candidate(run)]

            if not candidate_runs:
                logger.info(
                    "No eligible live/paper strategy runs found for "
                    "account. account_id=%s user_id=%s",
                    account_id,
                    user_id,
                )

                return StrategyDeploymentResult(
                    account_id=account_id,
                    deployed_strategy_ids=(),
                    skipped_strategy_ids=(),
                    failed_strategy_ids=(),
                )

            # Only resolve the account symbol universe when there is at
            # least one candidate actually assigned to this account.
            account_candidates = [
                run for run in candidate_runs if run.account_id == account_id
            ]

            account_symbols: tuple[str, ...] = ()

            if account_candidates:
                account_symbols = await self._resolve_account_symbols(
                    session=session,
                    account_id=account_id,
                )

                if not account_symbols:
                    raise StrategyDeploymentError(
                        f"Account '{account_id}' has eligible strategy "
                        "runs but no enabled AccountSymbol mappings. "
                        "At least one enabled account symbol is required "
                        "before live strategy deployment can start."
                    )

                logger.info(
                    "Resolved account symbol universe for strategy "
                    "deployment. account_id=%s symbols=%s",
                    account_id,
                    account_symbols,
                )

            for run in candidate_runs:
                strategy_id = str(
                    run.id,
                )

                try:
                    self._validate_account_assignment(
                        run=run,
                        account_id=account_id,
                    )

                    definition = await self._resolve_definition(
                        session=session,
                        run=run,
                    )

                    self._validate_definition(
                        run=run,
                        definition=definition,
                    )

                    config = self._build_config(
                        run=run,
                        definition=definition,
                        account_id=account_id,
                        symbols=account_symbols,
                    )

                except StrategyDeploymentError as exc:
                    logger.warning(
                        "Skipping strategy run because deployment "
                        "configuration is invalid. "
                        "strategy_run_id=%s account_id=%s reason=%s",
                        strategy_id,
                        account_id,
                        exc,
                    )

                    skipped.append(
                        strategy_id,
                    )
                    continue

                if strategy_manager.contains(
                    strategy_id,
                ):
                    logger.info(
                        "Strategy runtime already exists; "
                        "skipping deployment. "
                        "strategy_run_id=%s account_id=%s "
                        "strategy_name=%s",
                        strategy_id,
                        account_id,
                        run.strategy_name,
                    )

                    skipped.append(
                        strategy_id,
                    )
                    continue

                try:
                    instance = await strategy_manager.create(
                        config,
                        auto_start=False,
                    )

                    await strategy_manager.activate(
                        instance.strategy_id,
                    )

                    await strategy_manager.start_instance(
                        instance.strategy_id,
                    )

                    deployed.append(
                        strategy_id,
                    )

                    logger.info(
                        "Strategy deployed successfully. "
                        "strategy_run_id=%s strategy_name=%s "
                        "definition=%s version=%s "
                        "account_id=%s mode=%s symbols=%s "
                        "timeframes=%s",
                        strategy_id,
                        config.strategy_name,
                        definition.name,
                        definition.version,
                        account_id,
                        config.mode.value,
                        config.symbols,
                        config.timeframes,
                    )

                except Exception:
                    failed.append(
                        strategy_id,
                    )

                    logger.exception(
                        "Failed to deploy strategy run. "
                        "strategy_run_id=%s strategy_name=%s "
                        "account_id=%s",
                        strategy_id,
                        run.strategy_name,
                        account_id,
                    )

                    await self._cleanup_failed_instance(
                        strategy_manager=strategy_manager,
                        strategy_id=strategy_id,
                    )

        result = StrategyDeploymentResult(
            account_id=account_id,
            deployed_strategy_ids=tuple(
                deployed,
            ),
            skipped_strategy_ids=tuple(
                skipped,
            ),
            failed_strategy_ids=tuple(
                failed,
            ),
        )

        logger.info(
            "Strategy deployment completed. "
            "account_id=%s user_id=%s deployed=%s "
            "skipped=%s failed=%s",
            account_id,
            user_id,
            result.deployed_count,
            result.skipped_count,
            result.failed_count,
        )

        return result

    async def deploy_run(
        self,
        *,
        run: StrategyRun,
        account_id: UUID,
        user_id: UUID,
        strategy_manager: StrategyManager,
    ) -> str:
        """
        Deploy one explicitly selected StrategyRun.

        This method is useful for API-driven strategy start/stop
        operations.

        The supplied StrategyRun must belong to ``user_id`` and must
        reference an available, currently registered strategy
        definition.

        The strategy receives the complete enabled AccountSymbol
        universe for ``account_id``.
        """

        self._validate_inputs(
            account_id=account_id,
            user_id=user_id,
            strategy_manager=strategy_manager,
        )

        if run.user_id != user_id:
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' does not belong to " f"user '{user_id}'."
            )

        if not self._is_candidate(
            run,
        ):
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' is not deployable. "
                f"enabled={run.enabled!r}, "
                f"status={run.status!r}, "
                f"run_type={run.run_type!r}."
            )

        self._validate_account_assignment(
            run=run,
            account_id=account_id,
        )

        strategy_id = str(
            run.id,
        )

        if strategy_manager.contains(
            strategy_id,
        ):
            raise StrategyDeploymentError(
                f"Strategy runtime '{strategy_id}' already exists."
            )

        async with self.session_factory() as session:
            account_symbols = await self._resolve_account_symbols(
                session=session,
                account_id=account_id,
            )

            if not account_symbols:
                raise StrategyDeploymentError(
                    f"Account '{account_id}' has no enabled " "AccountSymbol mappings."
                )

            definition = await self._resolve_definition(
                session=session,
                run=run,
            )

            self._validate_definition(
                run=run,
                definition=definition,
            )

            config = self._build_config(
                run=run,
                definition=definition,
                account_id=account_id,
                symbols=account_symbols,
            )

        try:
            instance = await strategy_manager.create(
                config,
                auto_start=False,
            )

            await strategy_manager.activate(
                instance.strategy_id,
            )

            await strategy_manager.start_instance(
                instance.strategy_id,
            )

        except Exception as exc:
            await self._cleanup_failed_instance(
                strategy_manager=strategy_manager,
                strategy_id=strategy_id,
            )

            raise StrategyDeploymentError(
                f"Failed to deploy strategy run " f"'{strategy_id}'."
            ) from exc

        logger.info(
            "Strategy run deployed. "
            "strategy_run_id=%s strategy_name=%s "
            "definition=%s definition_version=%s "
            "account_id=%s user_id=%s symbols=%s",
            strategy_id,
            config.strategy_name,
            definition.name,
            definition.version,
            account_id,
            user_id,
            config.symbols,
        )

        return strategy_id

    # ==================================================================
    # ACCOUNT SYMBOL RESOLUTION
    # ==================================================================

    @staticmethod
    async def _resolve_account_symbols(
        *,
        session: AsyncSession,
        account_id: UUID,
    ) -> tuple[str, ...]:
        """
        Resolve the authoritative runtime symbol universe for an account.

        The returned values are canonical AQE symbols.

        Broker-facing symbols such as ``XAUUSD.s`` are deliberately not
        passed into StrategyConfig. AccountSymbolResolver owns the
        canonical-to-broker mapping used by downstream execution/data
        infrastructure.
        """

        resolver = AccountSymbolResolver(
            session,
        )

        try:
            symbols = await resolver.resolve_enabled_symbols(
                account_id=account_id,
            )

        except AccountSymbolResolutionError as exc:
            raise StrategyDeploymentError(
                f"Failed to resolve enabled account symbols for "
                f"account '{account_id}': {exc}"
            ) from exc

        normalized = tuple(
            dict.fromkeys(
                str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()
            )
        )

        return normalized

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_inputs(
        *,
        account_id: UUID,
        user_id: UUID,
        strategy_manager: StrategyManager,
    ) -> None:
        """Validate deployment dependencies."""

        if not isinstance(
            account_id,
            UUID,
        ):
            raise StrategyDeploymentError("account_id must be a UUID.")

        if not isinstance(
            user_id,
            UUID,
        ):
            raise StrategyDeploymentError("user_id must be a UUID.")

        if not isinstance(
            strategy_manager,
            StrategyManager,
        ):
            raise StrategyDeploymentError(
                "strategy_manager must be a StrategyManager instance."
            )

    @staticmethod
    def _is_candidate(
        run: StrategyRun,
    ) -> bool:
        """
        Return whether a StrategyRun should participate in deployment.

        Disabled StrategyRuns remain persisted but are never deployed.
        """

        if not run.enabled:
            return False

        if run.status != StrategyRunStatus.RUNNING:
            return False

        return run.run_type in {
            StrategyRunType.LIVE,
            StrategyRunType.PAPER,
        }

    # ==================================================================
    # STRATEGY DEFINITION
    # ==================================================================

    @staticmethod
    async def _resolve_definition(
        *,
        session: AsyncSession,
        run: StrategyRun,
    ) -> StrategyDefinition:
        """
        Resolve the persistent StrategyDefinition referenced by a run.
        """

        definition_id = run.strategy_definition_id

        if definition_id is None:
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' does not reference " "a strategy definition."
            )

        result = await session.execute(
            select(StrategyDefinition).where(
                StrategyDefinition.id == definition_id,
            )
        )

        definition = result.scalar_one_or_none()

        if definition is None:
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' references missing "
                f"strategy definition '{definition_id}'."
            )

        return definition

    def _validate_definition(
        self,
        *,
        run: StrategyRun,
        definition: StrategyDefinition,
    ) -> type[Any]:
        """
        Validate the persistent definition against the live registry.

        Returns:
            The currently registered strategy class.

        Validation covers:

            StrategyDefinition.available
                ↓
            registered implementation
                ↓
            definition name
                ↓
            definition version
                ↓
            implementation module
                ↓
            implementation class
        """

        if not definition.available:
            raise StrategyDeploymentError(
                f"Strategy definition '{definition.name}' " f"is unavailable."
            )

        try:
            strategy_class = self.registry.get(
                definition.name,
            )

        except Exception as exc:
            raise StrategyDeploymentError(
                f"Strategy '{definition.name}' is not currently "
                "registered in the AQE StrategyRegistry."
            ) from exc

        current_definition = getattr(
            strategy_class,
            "definition",
            None,
        )

        if current_definition is None:
            raise StrategyDeploymentError(
                f"Registered strategy '{definition.name}' does not "
                "expose a StrategyDefinition."
            )

        current_name = current_definition.name.strip()
        current_version = current_definition.version.strip()

        if current_name != definition.name.strip():
            raise StrategyDeploymentError(
                f"Strategy definition name mismatch for run "
                f"'{run.id}': database='{definition.name}' "
                f"registry='{current_name}'."
            )

        if current_version != definition.version.strip():
            raise StrategyDeploymentError(
                f"Strategy definition version mismatch for "
                f"'{definition.name}': database='{definition.version}' "
                f"registry='{current_version}'."
            )

        if strategy_class.__module__ != definition.module_path:
            raise StrategyDeploymentError(
                f"Strategy implementation module mismatch for "
                f"'{definition.name}': database="
                f"'{definition.module_path}' registry="
                f"'{strategy_class.__module__}'."
            )

        if strategy_class.__qualname__ != definition.class_name:
            raise StrategyDeploymentError(
                f"Strategy implementation class mismatch for "
                f"'{definition.name}': database="
                f"'{definition.class_name}' registry="
                f"'{strategy_class.__qualname__}'."
            )

        if run.strategy_name.strip().lower() != current_name.lower():
            raise StrategyDeploymentError(
                f"StrategyRun '{run.id}' strategy_name "
                f"'{run.strategy_name}' does not match "
                f"StrategyDefinition '{current_name}'."
            )

        if run.strategy_version.strip() != current_version:
            raise StrategyDeploymentError(
                f"StrategyRun '{run.id}' strategy_version "
                f"'{run.strategy_version}' does not match "
                f"StrategyDefinition version '{current_version}'."
            )

        return strategy_class

    @staticmethod
    def _validate_account_assignment(
        *,
        run: StrategyRun,
        account_id: UUID,
    ) -> None:
        """
        Validate that the StrategyRun belongs to the active account.

        StrategyRun.account_id is the authoritative account assignment.
        """

        if run.account_id is None:
            raise StrategyDeploymentError(f"Strategy run '{run.id}' has no account_id.")

        if run.account_id != account_id:
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' belongs to account "
                f"'{run.account_id}', but the active runtime account "
                f"is '{account_id}'."
            )

    # ==================================================================
    # CONFIGURATION
    # ==================================================================

    @classmethod
    def _build_config(
        cls,
        *,
        run: StrategyRun,
        definition: StrategyDefinition,
        account_id: UUID,
        symbols: Sequence[str],
    ) -> StrategyConfig:
        """
        Convert a persistent StrategyRun into StrategyConfig.

        AccountSymbol is the authoritative source for runtime symbols.

        ``run.symbols`` is intentionally not consulted here. It remains
        a persisted configuration/history snapshot and can therefore
        differ from the current enabled account symbol universe.

        The StrategyRun still owns:

            - strategy identity snapshot
            - strategy version snapshot
            - run name
            - description
            - notes
            - timeframe
            - parameters
            - account assignment
        """

        if run.account_id != account_id:
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' is assigned to account "
                f"'{run.account_id}', not '{account_id}'."
            )

        if not definition.available:
            raise StrategyDeploymentError(
                f"Strategy definition '{definition.name}' is unavailable."
            )

        if not run.run_name or not run.run_name.strip():
            raise StrategyDeploymentError(f"Strategy run '{run.id}' has no run_name.")

        if not run.strategy_name or not run.strategy_name.strip():
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' has no strategy_name."
            )

        if not run.strategy_version or not run.strategy_version.strip():
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' has no strategy_version."
            )

        normalized_symbols = tuple(
            dict.fromkeys(
                str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()
            )
        )

        if not normalized_symbols:
            raise StrategyDeploymentError(
                f"Account '{account_id}' has no valid enabled "
                f"symbols for strategy run '{run.id}'."
            )

        if not run.timeframe or not run.timeframe.strip():
            raise StrategyDeploymentError(
                f"Strategy run '{run.id}' has no timeframe configured."
            )

        parameters = dict(
            run.parameters or {},
        )

        mode = cls._resolve_mode(
            run.run_type,
        )

        metadata: dict[str, Any] = {
            "strategy_run_id": str(run.id),
            "strategy_definition_id": str(
                definition.id,
            ),
            "strategy_version": definition.version,
            "run_name": run.run_name,
            "symbol_source": "account_symbols",
        }

        if run.description:
            metadata["description"] = run.description

        if run.notes:
            metadata["notes"] = run.notes

        return StrategyConfig(
            strategy_id=str(run.id),
            strategy_name=definition.name.strip(),
            mode=mode,
            enabled=True,
            account_id=account_id,
            symbols=list(normalized_symbols),
            timeframes=[
                run.timeframe.strip().upper(),
            ],
            parameters=parameters,
            metadata=metadata,
        )

    @staticmethod
    def _resolve_mode(
        run_type: StrategyRunType,
    ) -> StrategyMode:
        """Map persistent StrategyRunType to runtime StrategyMode."""

        if run_type == StrategyRunType.LIVE:
            return StrategyMode.LIVE

        if run_type == StrategyRunType.PAPER:
            return StrategyMode.PAPER

        raise StrategyDeploymentError(
            f"Unsupported live deployment run type: {run_type!r}."
        )

    # ==================================================================
    # CLEANUP
    # ==================================================================

    @staticmethod
    async def _cleanup_failed_instance(
        *,
        strategy_manager: StrategyManager,
        strategy_id: str,
    ) -> None:
        """Remove a partially-created strategy runtime after failure."""

        try:
            if strategy_manager.contains(
                strategy_id,
            ):
                await strategy_manager.remove(
                    strategy_id,
                )

        except Exception:
            logger.exception(
                "Failed to clean up partially-created strategy runtime. "
                "strategy_id=%s",
                strategy_id,
            )


__all__ = [
    "LiveStrategyDeployer",
    "StrategyDeploymentError",
    "StrategyDeploymentResult",
]
