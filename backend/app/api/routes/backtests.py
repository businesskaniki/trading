"""API routes for persistent account-level AQE backtests."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_trading_account_service
from app.database.models.user import User
from app.database.session import get_db
from app.services.backtest_job_service import BacktestJobService
from app.services.trading_account_service import TradingAccountService
from app.tasks.backtests import execute_backtest_job

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/backtests",
    tags=["Backtests"],
)


class BacktestCreateRequest(BaseModel):
    """Request configuration for an account-level backtest."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID

    initial_balance: Decimal = Field(
        gt=Decimal("0"),
    )

    start: datetime
    end: datetime

    close_positions_at_end: bool = True


def _validate_period(*, start: datetime, end: datetime) -> None:
    """Validate the requested historical period."""

    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The backtest start time must be before the end time.",
        )


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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Persist a backtest job and return its ID without building the runtime.

    Historical preparation is performed later by the Celery worker.
    """

    _validate_period(
        start=request.start,
        end=request.end,
    )

    try:
        await trading_account_service.get_owned_account(
            account_id=request.account_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        job = await BacktestJobService.create(
            db,
            user_id=current_user.id,
            account_id=request.account_id,
            initial_balance=Decimal(str(request.initial_balance)),
            start=request.start,
            end=request.end,
            close_positions_at_end=request.close_positions_at_end,
        )

        logger.info(
            "Persistent backtest job created: " "job_id=%s account_id=%s user_id=%s",
            job.id,
            job.account_id,
            current_user.id,
        )

        return BacktestJobService.serialize(job)

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        await db.rollback()
        logger.exception(
            "Failed to create persistent backtest job: " "account_id=%s user_id=%s",
            request.account_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create the backtest job.",
        ) from exc


@router.get("")
async def list_backtests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return persisted backtest jobs belonging to the authenticated user."""

    jobs = await BacktestJobService.list_owned(
        db,
        user_id=current_user.id,
    )

    return [BacktestJobService.serialize(job) for job in jobs]


@router.get("/{backtest_id}")
async def get_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the latest persisted snapshot of an owned backtest."""

    try:
        job = await BacktestJobService.get_owned(
            db,
            backtest_id=backtest_id,
            user_id=current_user.id,
        )

        return BacktestJobService.serialize(job)

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/{backtest_id}/start")
async def start_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Queue a persisted job after its QUEUED transition has been committed.

    The HTTP response does not wait for data preparation or simulation.
    """

    task_id = str(backtest_id)

    try:
        job = await BacktestJobService.queue_owned(
            db,
            backtest_id=backtest_id,
            user_id=current_user.id,
            celery_task_id=task_id,
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

    try:
        execute_backtest_job.apply_async(
            args=[str(backtest_id)],
            task_id=task_id,
        )

    except Exception as exc:
        logger.exception(
            "Failed to enqueue backtest job: job_id=%s",
            backtest_id,
        )

        try:
            await BacktestJobService.mark_enqueue_failed(
                db,
                backtest_id=backtest_id,
                celery_task_id=task_id,
                error="Unable to enqueue the backtest worker task.",
            )
        except Exception:
            await db.rollback()
            logger.exception(
                "Failed to persist backtest enqueue failure: job_id=%s",
                backtest_id,
            )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The backtest was saved, but could not be queued. "
                "Check worker and Redis availability before retrying."
            ),
        ) from exc

    logger.info(
        "Backtest job queued: job_id=%s task_id=%s user_id=%s",
        backtest_id,
        task_id,
        current_user.id,
    )

    return BacktestJobService.serialize(job)


@router.post("/{backtest_id}/stop")
async def stop_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Request cooperative cancellation of an owned backtest."""

    try:
        job = await BacktestJobService.request_stop_owned(
            db,
            backtest_id=backtest_id,
            user_id=current_user.id,
        )

        return BacktestJobService.serialize(job)

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


@router.delete(
    "/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete an owned backtest that is no longer active."""

    try:
        await BacktestJobService.delete_owned(
            db,
            backtest_id=backtest_id,
            user_id=current_user.id,
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

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
