from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from backtesting.engine import BacktestConfig
from backtesting.service import BacktestService

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
    API request used to create a backtest.

    The request describes the simulation. BacktestService owns the
    lifecycle and BacktestOrchestrator owns strategy/risk/execution.
    """

    model_config = ConfigDict(extra="forbid")

    account_id: UUID

    initial_balance: Decimal = Field(
        gt=Decimal("0"),
    )

    symbols: list[str] = Field(
        min_length=1,
    )

    timeframes: list[str] = Field(
        min_length=1,
    )

    start: datetime | None = None
    end: datetime | None = None

    strategy_id: str = Field(
        min_length=1,
        max_length=128,
    )

    strategy_name: str = Field(
        min_length=1,
        max_length=128,
    )

    close_positions_at_end: bool = True

    contract_sizes: dict[str, Decimal] = Field(
        default_factory=dict,
    )


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_backtest_service() -> BacktestService:
    """
    Return the application-level BacktestService.
    """

    from app.core.backtesting import get_backtest_service as get_service

    return get_service()


# ---------------------------------------------------------------------------
# Request → domain conversion
# ---------------------------------------------------------------------------


def _build_backtest_config(
    request: BacktestCreateRequest,
) -> BacktestConfig:
    """
    Convert the HTTP request into the immutable BacktestConfig domain
    object.
    """

    symbols = tuple(
        symbol.strip().upper()
        for symbol in request.symbols
        if symbol and symbol.strip()
    )

    timeframes = tuple(
        timeframe.strip().upper()
        for timeframe in request.timeframes
        if timeframe and timeframe.strip()
    )

    if not symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one symbol is required.",
        )

    if not timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one timeframe is required.",
        )

    if (
        request.start is not None
        and request.end is not None
        and request.start >= request.end
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The backtest start time must be before the end time.",
        )

    strategy_id = request.strategy_id.strip()
    strategy_name = request.strategy_name.strip()

    if not strategy_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="strategy_id cannot be empty.",
        )

    if not strategy_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="strategy_name cannot be empty.",
        )

    contract_sizes: dict[str, Decimal] = {}

    for symbol, contract_size in request.contract_sizes.items():
        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contract-size symbols cannot be empty.",
            )

        if contract_size <= Decimal("0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Contract size for '{normalized_symbol}' "
                    "must be greater than zero."
                ),
            )

        contract_sizes[normalized_symbol] = contract_size

    return BacktestConfig(
        account_id=request.account_id,
        initial_balance=request.initial_balance,
        symbols=symbols,
        timeframes=timeframes,
        start=request.start,
        end=request.end,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        close_positions_at_end=request.close_positions_at_end,
        contract_sizes=contract_sizes,
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
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    """
    Create a backtest without starting it.

    The returned run remains in CREATED state until /start is called.
    """

    config = _build_backtest_config(request)

    logger.info(
        "Creating backtest: "
        "account_id=%s strategy_id=%s strategy_name=%s "
        "symbols=%s timeframes=%s start=%s end=%s",
        config.account_id,
        config.strategy_id,
        config.strategy_name,
        config.symbols,
        config.timeframes,
        config.start,
        config.end,
    )

    try:
        result = await service.create(config)

        logger.info(
            "Backtest created successfully: " "account_id=%s strategy_id=%s",
            config.account_id,
            config.strategy_id,
        )

        return result

    except ValueError as exc:
        logger.warning(
            "Backtest validation failed: " "account_id=%s strategy_id=%s error=%s",
            config.account_id,
            config.strategy_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        logger.warning(
            "Backtest creation conflict: " "account_id=%s strategy_id=%s error=%s",
            config.account_id,
            config.strategy_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        # This is the important change.
        #
        # logger.exception() records the complete traceback, including
        # the exact file and line where the backtest creation failed.
        logger.exception(
            "Unexpected error while creating backtest: "
            "account_id=%s strategy_id=%s strategy_name=%s",
            config.account_id,
            config.strategy_id,
            config.strategy_name,
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
    service: BacktestService = Depends(get_backtest_service),
) -> list[dict]:
    """
    Return all registered backtests.

    Newest runs are returned first.
    """

    return await service.list()


@router.get(
    "/{backtest_id}",
)
async def get_backtest(
    backtest_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    """
    Return the current state of one backtest.
    """

    try:
        return await service.get(backtest_id)

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
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    """
    Start a CREATED backtest in the background.
    """

    try:
        return await service.start(backtest_id)

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

    except Exception:
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
        )


@router.post(
    "/{backtest_id}/stop",
)
async def stop_backtest(
    backtest_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    """
    Request cooperative shutdown of a running backtest.
    """

    try:
        return await service.stop(backtest_id)

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

    except Exception:
        logger.exception(
            "Unexpected error while stopping backtest: " "backtest_id=%s",
            backtest_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to stop backtest. " "Check backend logs for the full exception."
            ),
        )


@router.delete(
    "/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_backtest(
    backtest_id: UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> Response:
    """
    Remove a completed, stopped, or failed backtest from the
    in-memory registry.
    """

    try:
        await service.remove(backtest_id)

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

    except Exception:
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
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
