"""API routes for account-level AQE backtesting."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from backtesting.engine import BacktestConfig
from backtesting.service import BacktestService

from app.api.dependencies import get_current_user
from app.api.dependencies import get_trading_account_service
from app.database.models.user import User
from app.services.trading_account_service import TradingAccountService

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/backtests",
    tags=["Backtests"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class BacktestCreateRequest(BaseModel):
    """
    Public API request for an account-level backtest.

    Strategy configuration, account symbols, timeframes, and instrument
    metadata are resolved internally from the persisted account state.

    The authenticated user is never supplied by the client.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    account_id: UUID

    initial_balance: Decimal = Field(
        gt=Decimal("0"),
    )

    start: datetime

    end: datetime

    close_positions_at_end: bool = True


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_backtest_service() -> BacktestService:
    """
    Return the application-level BacktestService.
    """

    from app.core.backtesting import (
        get_backtest_service as get_service,
    )

    return get_service()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_period(
    *,
    start: datetime,
    end: datetime,
) -> None:
    """
    Validate the requested historical simulation period.
    """

    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The backtest start time must be before the end time.",
        )


# ---------------------------------------------------------------------------
# Request -> domain conversion
# ---------------------------------------------------------------------------


def _build_backtest_config(
    request: BacktestCreateRequest,
    *,
    user_id: UUID,
) -> BacktestConfig:
    """
    Convert the public API request into the internal BacktestConfig.

    The API deliberately provides no strategy or symbol selection.

    Those values are resolved later by BacktestComposition from:

        StrategyRun
            +
        AccountSymbol
    """

    _validate_period(
        start=request.start,
        end=request.end,
    )

    return BacktestConfig(
        account_id=request.account_id,
        initial_balance=Decimal(
            str(request.initial_balance),
        ),
        symbols=(),
        timeframes=(),
        start=request.start,
        end=request.end,
        contract_sizes={},
        close_positions_at_end=request.close_positions_at_end,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_backtest(
    request: BacktestCreateRequest,
    current_user: User = Depends(get_current_user),
    trading_account_service: TradingAccountService = Depends(
        get_trading_account_service,
    ),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> dict:
    """
    Create an account-level backtest without starting it.

    The requested trading account must belong to the authenticated user.

    The created run remains in CREATED state until /start is called.
    """

    # ==============================================================
    # 1. Validate requested period
    # ==============================================================

    _validate_period(
        start=request.start,
        end=request.end,
    )

    # ==============================================================
    # 2. Verify account ownership
    # ==============================================================

    try:
        account = await trading_account_service.get_owned_account(
            account_id=request.account_id,
            user_id=current_user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # ==============================================================
    # 3. Build internal domain configuration
    # ==============================================================

    config = _build_backtest_config(
        request,
        user_id=current_user.id,
    )

    logger.info(
        "Creating account-level backtest: "
        "account_id=%s user_id=%s start=%s end=%s "
        "initial_balance=%s close_positions_at_end=%s",
        config.account_id,
        current_user.id,
        config.start,
        config.end,
        config.initial_balance,
        config.close_positions_at_end,
    )

    try:
        result = await service.create(
            config,
        )

        logger.info(
            "Backtest created successfully: " "account_id=%s user_id=%s backtest=%s",
            account.id,
            current_user.id,
            result,
        )

        return result

    except ValueError as exc:
        logger.warning(
            "Backtest validation failed: " "account_id=%s user_id=%s error=%s",
            config.account_id,
            current_user.id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        logger.warning(
            "Backtest creation conflict: " "account_id=%s user_id=%s error=%s",
            config.account_id,
            current_user.id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected error while creating backtest: " "account_id=%s user_id=%s",
            config.account_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to create backtest. "
                "Check backend logs for the full exception."
            ),
        ) from exc


@router.get(
    "",
)
async def list_backtests(
    current_user: User = Depends(get_current_user),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> list[dict]:
    """
    Return backtests currently registered by the application.

    BacktestService currently owns an application-level in-memory
    registry. User-level filtering can be added there once persistent
    backtest ownership is introduced.
    """

    del current_user

    return await service.list()


@router.get(
    "/{backtest_id}",
)
async def get_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> dict:
    """
    Return the current state of one backtest.

    Ownership enforcement for persisted backtest records should be added
    once BacktestRun persistence is introduced.
    """

    del current_user

    try:
        return await service.get(
            backtest_id,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{backtest_id}/start",
)
async def start_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> dict:
    """
    Start a CREATED backtest.

    BacktestService owns the execution lifecycle.
    """

    del current_user

    try:
        return await service.start(
            backtest_id,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected error while starting backtest: " "backtest_id=%s",
            backtest_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to start backtest. "
                "Check backend logs for the full exception."
            ),
        ) from exc


@router.post(
    "/{backtest_id}/stop",
)
async def stop_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> dict:
    """
    Request cooperative shutdown of a running backtest.
    """

    del current_user

    try:
        return await service.stop(
            backtest_id,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected error while stopping backtest: " "backtest_id=%s",
            backtest_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to stop backtest. " "Check backend logs for the full exception."
            ),
        ) from exc


@router.delete(
    "/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BacktestService = Depends(
        get_backtest_service,
    ),
) -> Response:
    """
    Remove a completed, stopped, or failed backtest from the
    in-memory registry.
    """

    del current_user

    try:
        await service.remove(
            backtest_id,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected error while deleting backtest: " "backtest_id=%s",
            backtest_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to delete backtest. "
                "Check backend logs for the full exception."
            ),
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
