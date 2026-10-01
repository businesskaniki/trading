"""API routes for live AQE strategy runtime lifecycle management."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import get_current_user
from app.core.engine import get_aqe_engine
from app.database.models.user import User
from app.database.session import SessionLocal
from app.repositories.strategy_run_repository import StrategyRunRepository
from engine.enums import EngineStatus
from engine.exceptions import EngineStateError
from strategies.core import StrategyMode, StrategyStatus
from strategies.core.exceptions import StrategyStateError

router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
)


class StrategyLifecycleAction(StrEnum):
    """Supported runtime lifecycle actions."""

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    PAUSE = "pause"
    RESUME = "resume"


class StrategyRuntimeResponse(BaseModel):
    """Current runtime state of one strategy instance."""

    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    strategy_name: str
    mode: StrategyMode
    status: StrategyStatus
    enabled: bool
    active: bool
    account_id: UUID | None
    symbols: list[str]
    timeframes: list[str]

    @classmethod
    def from_instance(
        cls,
        instance: Any,
    ) -> "StrategyRuntimeResponse":
        """Build an API response from a StrategyInstance."""

        account_id = instance.config.account_id

        return cls(
            strategy_id=str(instance.strategy_id),
            strategy_name=instance.strategy_name,
            mode=instance.mode,
            status=instance.status,
            enabled=instance.is_enabled,
            active=instance.is_active,
            account_id=account_id,
            symbols=list(instance.symbols),
            timeframes=list(instance.timeframes),
        )


class StrategyLifecycleResponse(BaseModel):
    """Result returned after a lifecycle operation."""

    strategy_id: str
    strategy_name: str
    action: StrategyLifecycleAction
    mode: StrategyMode
    status: StrategyStatus
    enabled: bool
    active: bool
    account_id: UUID | None

    @classmethod
    def from_instance(
        cls,
        *,
        instance: Any,
        action: StrategyLifecycleAction,
    ) -> "StrategyLifecycleResponse":
        """Build a lifecycle response from a StrategyInstance."""

        return cls(
            strategy_id=str(instance.strategy_id),
            strategy_name=instance.strategy_name,
            action=action,
            mode=instance.mode,
            status=instance.status,
            enabled=instance.is_enabled,
            active=instance.is_active,
            account_id=instance.config.account_id,
        )


def _require_engine_running() -> Any:
    """
    Return the active AQE engine.

    Per-strategy runtime operations require an active engine because
    StrategyManager instances exist only inside the active
    ExecutionRuntime.
    """

    engine = get_aqe_engine()

    if engine.context.status not in {
        EngineStatus.RUNNING,
        EngineStatus.PAUSED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "AQE engine is not running. "
                f"Current state={engine.context.status.value}."
            ),
        )

    return engine


async def _get_owned_runtime_strategy(
    *,
    strategy_id: str,
    current_user: User,
) -> tuple[Any, Any]:
    """
    Resolve a runtime strategy and verify authenticated ownership.

    Returns:

        (engine, strategy_instance)
    """

    engine = _require_engine_running()

    strategy_manager = engine.strategy_manager

    if strategy_manager is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AQE strategy runtime is not configured.",
        )

    try:
        strategy_uuid = UUID(
            str(strategy_id),
        )

    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="strategy_id must be a valid UUID.",
        ) from exc

    # --------------------------------------------------------------
    # Verify persistent ownership.
    #
    # Runtime strategy_id is the StrategyRun UUID.
    # --------------------------------------------------------------

    async with SessionLocal() as session:
        repository = StrategyRunRepository(
            session,
        )

        strategy_run = await repository.get_by_id(
            strategy_run_id=strategy_uuid,
            user_id=current_user.id,
        )

    if strategy_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Strategy '{strategy_id}' was not found " "for the authenticated user."
            ),
        )

    instance = strategy_manager.get(
        str(strategy_uuid),
    )

    if instance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Strategy '{strategy_id}' is not currently "
                "deployed in the AQE runtime."
            ),
        )

    # --------------------------------------------------------------
    # Defensive account boundary.
    #
    # A runtime may only control a strategy assigned to the account
    # currently owned by AQEEngine.
    # --------------------------------------------------------------

    runtime_account_id = engine.context.account_id
    strategy_account_id = instance.config.account_id

    if runtime_account_id is not None and strategy_account_id != runtime_account_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Strategy '{strategy_id}' is assigned to account "
                f"'{strategy_account_id}', while the active AQE runtime "
                f"uses account '{runtime_account_id}'."
            ),
        )

    return engine, instance


@router.get(
    "",
    response_model=list[StrategyRuntimeResponse],
)
async def list_runtime_strategies(
    current_user: User = Depends(get_current_user),
) -> list[StrategyRuntimeResponse]:
    """
    Return runtime strategies belonging to the authenticated user.

    Only strategies currently deployed in the active AQE runtime are
    returned.
    """

    engine = _require_engine_running()

    strategy_manager = engine.strategy_manager

    if strategy_manager is None:
        return []

    runtime_account_id = engine.context.account_id

    async with SessionLocal() as session:
        repository = StrategyRunRepository(
            session,
        )

        runs = await repository.get_all(
            user_id=current_user.id,
        )

    owned_run_ids = {
        str(run.id)
        for run in runs
        if isinstance(run.parameters, dict)
        and run.parameters.get("account_id") is not None
        and runtime_account_id is not None
        and str(run.parameters.get("account_id")) == str(runtime_account_id)
    }

    instances = []

    for instance in strategy_manager.instances():
        if str(instance.strategy_id) not in owned_run_ids:
            continue

        if (
            runtime_account_id is not None
            and instance.config.account_id != runtime_account_id
        ):
            continue

        instances.append(
            StrategyRuntimeResponse.from_instance(
                instance,
            )
        )

    return instances


@router.get(
    "/{strategy_id}",
    response_model=StrategyRuntimeResponse,
)
async def get_runtime_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
) -> StrategyRuntimeResponse:
    """Return one deployed runtime strategy."""

    _, instance = await _get_owned_runtime_strategy(
        strategy_id=strategy_id,
        current_user=current_user,
    )

    return StrategyRuntimeResponse.from_instance(
        instance,
    )


@router.post(
    "/{strategy_id}/activate",
    response_model=StrategyLifecycleResponse,
)
async def activate_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
) -> StrategyLifecycleResponse:
    """
    Activate one strategy instance.

    Activation enables the strategy for market-data processing but does
    not alter its lifecycle status.
    """

    engine, instance = await _get_owned_runtime_strategy(
        strategy_id=strategy_id,
        current_user=current_user,
    )

    strategy_manager = engine.strategy_manager

    assert strategy_manager is not None

    try:
        instance = await strategy_manager.activate(
            strategy_id,
        )

    except StrategyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return StrategyLifecycleResponse.from_instance(
        instance=instance,
        action=StrategyLifecycleAction.ACTIVATE,
    )


@router.post(
    "/{strategy_id}/deactivate",
    response_model=StrategyLifecycleResponse,
)
async def deactivate_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
) -> StrategyLifecycleResponse:
    """
    Deactivate one strategy instance.

    Deactivation disables market-data processing while leaving the
    strategy lifecycle running.
    """

    engine, instance = await _get_owned_runtime_strategy(
        strategy_id=strategy_id,
        current_user=current_user,
    )

    strategy_manager = engine.strategy_manager

    assert strategy_manager is not None

    try:
        instance = await strategy_manager.deactivate(
            strategy_id,
        )

    except StrategyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return StrategyLifecycleResponse.from_instance(
        instance=instance,
        action=StrategyLifecycleAction.DEACTIVATE,
    )


@router.post(
    "/{strategy_id}/pause",
    response_model=StrategyLifecycleResponse,
)
async def pause_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
) -> StrategyLifecycleResponse:
    """
    Pause one strategy lifecycle.

    PAUSED strategies do not process incoming market data.
    """

    engine, instance = await _get_owned_runtime_strategy(
        strategy_id=strategy_id,
        current_user=current_user,
    )

    strategy_manager = engine.strategy_manager

    assert strategy_manager is not None

    if instance.mode not in {
        StrategyMode.LIVE,
        StrategyMode.PAPER,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only LIVE and PAPER strategies can be "
                "paused through the live runtime API."
            ),
        )

    try:
        instance = await strategy_manager.pause_instance(
            strategy_id,
        )

    except StrategyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return StrategyLifecycleResponse.from_instance(
        instance=instance,
        action=StrategyLifecycleAction.PAUSE,
    )


@router.post(
    "/{strategy_id}/resume",
    response_model=StrategyLifecycleResponse,
)
async def resume_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
) -> StrategyLifecycleResponse:
    """
    Resume one paused strategy lifecycle.
    """

    engine, instance = await _get_owned_runtime_strategy(
        strategy_id=strategy_id,
        current_user=current_user,
    )

    strategy_manager = engine.strategy_manager

    assert strategy_manager is not None

    if instance.mode not in {
        StrategyMode.LIVE,
        StrategyMode.PAPER,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only LIVE and PAPER strategies can be "
                "resumed through the live runtime API."
            ),
        )

    try:
        instance = await strategy_manager.resume_instance(
            strategy_id,
        )

    except StrategyStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return StrategyLifecycleResponse.from_instance(
        instance=instance,
        action=StrategyLifecycleAction.RESUME,
    )


__all__ = [
    "router",
    "StrategyLifecycleAction",
    "StrategyLifecycleResponse",
    "StrategyRuntimeResponse",
]
