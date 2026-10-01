"""Business logic for account-scoped AQE strategy runs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.database.models.strategy_definition import StrategyDefinition
from app.repositories.strategy_run_repository import StrategyRunRepository
from app.repositories.trading_account_repository import TradingAccountRepository
from app.schemas.strategy_run import (
    StrategyRunCreate,
    StrategyRunUpdate,
)


class StrategyRunService:
    """
    Business logic for persisted strategy runs.

    A StrategyRun is an account-specific assignment of an installed
    StrategyDefinition.

    Responsibilities:
        - validate authenticated ownership
        - validate strategy-definition identity
        - create immutable strategy snapshots
        - enforce immutable run identity
        - normalize persisted configuration
        - coordinate repository access

    This service does not:
        - discover Python strategies
        - start strategy instances
        - calculate risk
        - execute orders
        - communicate with brokers
    """

    def __init__(
        self,
        repository: StrategyRunRepository,
        account_repository: TradingAccountRepository | None = None,
    ) -> None:
        self.repository = repository
        self.account_repository = account_repository

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_strategy_run(
        self,
        data: StrategyRunCreate,
        *,
        user_id: UUID,
        commit: bool = True,
    ):
        """
        Create a new StrategyRun for an account owned by the user.

        The client selects the StrategyDefinition by ID.

        The service derives and persists:

            strategy_name
            strategy_version

        from the authoritative StrategyDefinition catalog row.
        """

        self._validate_user_id(user_id)

        account_id = self._validate_uuid(
            data.account_id,
            "account_id",
        )

        strategy_definition_id = self._validate_uuid(
            data.strategy_definition_id,
            "strategy_definition_id",
        )

        # ------------------------------------------------------
        # Account ownership
        # ------------------------------------------------------

        await self._validate_account_ownership(
            account_id=account_id,
            user_id=user_id,
        )

        # ------------------------------------------------------
        # Strategy definition
        # ------------------------------------------------------

        strategy_definition = await self._resolve_strategy_definition(
            strategy_definition_id,
        )

        self._validate_strategy_definition(
            strategy_definition,
        )

        # ------------------------------------------------------
        # Build persisted payload
        # ------------------------------------------------------

        payload = data.model_dump()

        payload["account_id"] = account_id
        payload["strategy_definition_id"] = strategy_definition.id

        # ------------------------------------------------------
        # Strategy identity is always derived from the catalog.
        # Never trust client-supplied identity fields.
        # ------------------------------------------------------

        payload["strategy_name"] = strategy_definition.name.strip()

        payload["strategy_version"] = strategy_definition.version.strip()

        payload["symbols"] = self._normalize_symbols(
            payload.get("symbols"),
        )

        payload["run_name"] = self._normalize_required_string(
            payload.get("run_name"),
            "run_name",
        )

        payload["description"] = self._normalize_optional_string(
            payload.get("description"),
        )

        payload["timeframe"] = self._normalize_required_string(
            payload.get("timeframe"),
            "timeframe",
        ).upper()

        payload["parameters"] = self._normalize_parameters(
            payload.get("parameters"),
        )

        payload["notes"] = self._normalize_optional_string(
            payload.get("notes"),
        )

        return await self.repository.create(
            user_id=user_id,
            commit=commit,
            **payload,
        )

    # ==========================================================
    # READ
    # ==========================================================

    async def get_strategy_run(
        self,
        strategy_run_id: UUID,
        *,
        user_id: UUID,
    ):
        """
        Retrieve one StrategyRun owned by the authenticated user.
        """

        self._validate_user_id(user_id)

        strategy_run_id = self._validate_uuid(
            strategy_run_id,
            "strategy_run_id",
        )

        strategy_run = await self.repository.get_by_id(
            strategy_run_id,
        )

        if strategy_run is None:
            raise ValueError("Strategy run not found")

        if strategy_run.user_id != user_id:
            raise ValueError("Strategy run not found")

        return strategy_run

    async def get_strategy_runs(
        self,
        *,
        user_id: UUID,
    ):
        """
        Retrieve all strategy runs belonging to the authenticated user.
        """

        self._validate_user_id(user_id)

        return await self.repository.get_all(
            user_id=user_id,
        )

    async def get_by_name(
        self,
        strategy_name: str,
        *,
        user_id: UUID,
    ):
        """
        Retrieve runs using the persisted strategy-name snapshot.

        This is a convenience query only. The authoritative strategy
        identity remains strategy_definition_id.
        """

        self._validate_user_id(user_id)

        strategy_name = self._normalize_required_string(
            strategy_name,
            "strategy_name",
        )

        return await self.repository.get_by_name(
            strategy_name,
            user_id=user_id,
        )

    async def get_by_status(
        self,
        status,
        *,
        user_id: UUID,
    ):
        """
        Retrieve runs for the authenticated user filtered by status.
        """

        self._validate_user_id(user_id)

        return await self.repository.get_by_status(
            status,
            user_id=user_id,
        )

    async def get_by_type(
        self,
        run_type,
        *,
        user_id: UUID,
    ):
        """
        Retrieve runs for the authenticated user filtered by run type.
        """

        self._validate_user_id(user_id)

        return await self.repository.get_by_type(
            run_type,
            user_id=user_id,
        )

    async def get_enabled_for_account(
        self,
        account_id: UUID,
        *,
        user_id: UUID,
    ):
        """
        Retrieve enabled strategy runs for a user-owned account.

        This is the primary lookup used by the account-level runtime
        and backtesting composition layers.
        """

        self._validate_user_id(user_id)

        account_id = self._validate_uuid(
            account_id,
            "account_id",
        )

        await self._validate_account_ownership(
            account_id=account_id,
            user_id=user_id,
        )

        return await self.repository.get_enabled_for_account(
            account_id=account_id,
            user_id=user_id,
        )

    async def get_latest(
        self,
        strategy_name: str,
        *,
        user_id: UUID,
    ):
        """
        Retrieve the latest run using the persisted strategy-name
        snapshot.
        """

        self._validate_user_id(user_id)

        strategy_name = self._normalize_required_string(
            strategy_name,
            "strategy_name",
        )

        return await self.repository.get_latest(
            strategy_name,
            user_id=user_id,
        )

    async def get_latest_for_user(
        self,
        *,
        user_id: UUID,
    ):
        """
        Retrieve the latest strategy runs for the authenticated user.
        """

        self._validate_user_id(user_id)

        return await self.repository.get_latest_for_user(
            user_id=user_id,
        )

    async def get_running_for_user(
        self,
        *,
        user_id: UUID,
    ):
        """
        Retrieve running strategy runs for the authenticated user.
        """

        self._validate_user_id(user_id)

        return await self.repository.get_running_for_user(
            user_id=user_id,
        )

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_strategy_run(
        self,
        strategy_run_id: UUID,
        data: StrategyRunUpdate,
        *,
        user_id: UUID,
        commit: bool = True,
    ):
        """
        Update a StrategyRun.

        Strategy/account identity is immutable after creation.

        Immutable fields:

            account_id
            strategy_definition_id
            strategy_name
            strategy_version
        """

        self._validate_user_id(user_id)

        strategy_run_id = self._validate_uuid(
            strategy_run_id,
            "strategy_run_id",
        )

        strategy_run = await self.get_strategy_run(
            strategy_run_id,
            user_id=user_id,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        # ------------------------------------------------------
        # Defense in depth.
        #
        # These fields should already be absent from the schema,
        # but reject them if a lower-level caller supplies a model
        # containing them in the future.
        # ------------------------------------------------------

        immutable_fields = (
            "account_id",
            "strategy_definition_id",
            "strategy_name",
            "strategy_version",
        )

        for field_name in immutable_fields:
            if field_name in update_data:
                raise ValueError(
                    f"'{field_name}' cannot be changed after "
                    "strategy-run creation. Create a new strategy run "
                    "instead."
                )

        if not update_data:
            return strategy_run

        # ------------------------------------------------------
        # Normalize mutable fields
        # ------------------------------------------------------

        if "run_name" in update_data:
            update_data["run_name"] = self._normalize_required_string(
                update_data["run_name"],
                "run_name",
            )

        if "description" in update_data:
            update_data["description"] = self._normalize_optional_string(
                update_data["description"],
            )

        if "parameters" in update_data:
            update_data["parameters"] = self._normalize_parameters(
                update_data["parameters"],
            )

        if "symbols" in update_data:
            update_data["symbols"] = self._normalize_symbols(
                update_data["symbols"],
            )

        if "timeframe" in update_data:
            update_data["timeframe"] = self._normalize_required_string(
                update_data["timeframe"],
                "timeframe",
            ).upper()

        if "notes" in update_data:
            update_data["notes"] = self._normalize_optional_string(
                update_data["notes"],
            )

        return await self.repository.update(
            strategy_run,
            commit=commit,
            **update_data,
        )

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_strategy_run(
        self,
        strategy_run_id: UUID,
        *,
        user_id: UUID,
        commit: bool = True,
    ) -> None:
        """
        Delete a StrategyRun owned by the authenticated user.
        """

        self._validate_user_id(user_id)

        strategy_run_id = self._validate_uuid(
            strategy_run_id,
            "strategy_run_id",
        )

        strategy_run = await self.get_strategy_run(
            strategy_run_id,
            user_id=user_id,
        )

        await self.repository.delete(
            strategy_run,
            commit=commit,
        )

    # ==========================================================
    # STRATEGY-DEFINITION RESOLUTION
    # ==========================================================

    async def _resolve_strategy_definition(
        self,
        strategy_definition_id: UUID,
    ) -> StrategyDefinition:
        """
        Resolve the persistent StrategyDefinition catalog row.

        Availability is deliberately validated separately so that
        repository lookup remains a data-access concern.
        """

        strategy_definition = await self.repository.get_strategy_definition_by_id(
            strategy_definition_id,
        )

        if strategy_definition is None:
            raise ValueError(
                "Strategy definition not found",
            )

        return strategy_definition

    @staticmethod
    def _validate_strategy_definition(
        strategy_definition: StrategyDefinition,
    ) -> None:
        """
        Validate that the selected installed strategy is usable.
        """

        if not strategy_definition.available:
            raise ValueError(
                f"Strategy '{strategy_definition.name}' is not currently " "available."
            )

        name = strategy_definition.name.strip()
        version = strategy_definition.version.strip()

        if not name:
            raise ValueError(
                "Strategy definition has an empty name.",
            )

        if not version:
            raise ValueError(
                f"Strategy '{name}' has an empty version.",
            )

        module_path = strategy_definition.module_path.strip()
        class_name = strategy_definition.class_name.strip()

        if not module_path:
            raise ValueError(
                f"Strategy '{name}' has an empty module path.",
            )

        if not class_name:
            raise ValueError(
                f"Strategy '{name}' has an empty class name.",
            )

    # ==========================================================
    # ACCOUNT OWNERSHIP
    # ==========================================================

    async def _validate_account_ownership(
        self,
        *,
        account_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Ensure the trading account belongs to the authenticated user.

        This check is mandatory for API-level account assignment.
        """

        if self.account_repository is None:
            raise RuntimeError(
                "StrategyRunService requires a "
                "TradingAccountRepository for account ownership "
                "validation."
            )

        account = await self.account_repository.get_by_id_and_user(
            account_id,
            user_id,
        )

        if account is None:
            raise ValueError(
                "Trading account not found",
            )

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_symbols(
        values: Any,
    ) -> list[str]:
        """
        Normalize a historical symbol snapshot.

        Rules:
            - None -> []
            - values must be iterable
            - symbols must be strings
            - whitespace is removed
            - symbols are uppercased
            - empty values are discarded
            - duplicates are removed
            - first-seen order is preserved
        """

        if values is None:
            return []

        if isinstance(values, str):
            values = [values]

        try:
            iterator = iter(values)
        except TypeError as exc:
            raise ValueError(
                "symbols must be a list of strings.",
            ) from exc

        result: list[str] = []
        seen: set[str] = set()

        for value in iterator:
            if not isinstance(value, str):
                raise ValueError(
                    "symbols must contain only strings.",
                )

            symbol = value.strip().upper()

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            result.append(symbol)

        return result

    @staticmethod
    def _normalize_parameters(
        value: Any,
    ) -> dict[str, Any]:
        """
        Normalize strategy parameters.
        """

        if value is None:
            return {}

        if not isinstance(value, dict):
            raise ValueError(
                "parameters must be an object.",
            )

        return dict(value)

    @staticmethod
    def _normalize_required_string(
        value: Any,
        field_name: str,
    ) -> str:
        """
        Normalize a required string field.
        """

        if not isinstance(value, str):
            raise ValueError(
                f"{field_name} must be a string.",
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} cannot be empty.",
            )

        return normalized

    @staticmethod
    def _normalize_optional_string(
        value: Any,
    ) -> str | None:
        """
        Normalize an optional string.
        """

        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                "Value must be a string or null.",
            )

        normalized = value.strip()

        return normalized or None

    # ==========================================================
    # VALIDATION HELPERS
    # ==========================================================

    @staticmethod
    def _validate_uuid(
        value: Any,
        field_name: str,
    ) -> UUID:
        """
        Validate and normalize UUID values.
        """

        if isinstance(value, UUID):
            return value

        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                f"{field_name} must be a valid UUID.",
            ) from exc

    @staticmethod
    def _validate_user_id(
        user_id: Any,
    ) -> UUID:
        """
        Validate authenticated user identity.
        """

        return StrategyRunService._validate_uuid(
            user_id,
            "user_id",
        )
