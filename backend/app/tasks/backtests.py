"""Celery worker tasks for durable AQE backtests."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.backtesting import create_backtest_service
from app.core.celery import celery_app
from app.database.models.backtest_job import BacktestJob
from app.database.session import SessionLocal
from app.services.backtest_job_service import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    BacktestJobService,
    append_backtest_status_history,
)
from backtesting.engine import BacktestConfig

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0

RUNTIME_TERMINAL_STATUSES = frozenset(
    {
        "COMPLETED",
        "STOPPED",
        "FAILED",
    }
)

TERMINAL_TASK_STATES = frozenset(
    {
        "COMPLETED",
        "CANCELLED",
        "CANCELED",
        "STOPPED",
        "FAILED",
    }
)


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize database datetimes to timezone-aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _merge_snapshot(
    existing_snapshot: dict[str, Any] | None,
    runtime_snapshot: dict[str, Any] | None,
    *,
    status: str,
    phase: str,
    cancel_requested: bool,
    error: str | None,
) -> dict[str, Any]:
    """
    Merge runtime data into the persistent job snapshot.

    The persistent lifecycle history is authoritative. It must survive
    snapshots returned by the in-memory BacktestService, because those
    snapshots do not own the durable Celery job lifecycle.
    """

    if existing_snapshot is not None:
        persisted_snapshot = dict(existing_snapshot)
    else:
        persisted_snapshot = {}

    existing_history = persisted_snapshot.get("status_history")

    if isinstance(existing_history, list):
        history = [dict(entry) for entry in existing_history if isinstance(entry, dict)]
    else:
        history = []

    if isinstance(runtime_snapshot, dict):
        for key, value in runtime_snapshot.items():
            if key != "status_history":
                persisted_snapshot[key] = value

    # Restore persistent history after merging the runtime snapshot.
    persisted_snapshot["status_history"] = history

    persisted_snapshot = append_backtest_status_history(
        persisted_snapshot,
        status=status,
        phase=phase,
    )

    task_states = {
        "QUEUED": "running",
        "BACKTEST_CREATED": "running",
        "RUNNING": "running",
        "COMPLETED": "completed",
        "STOPPED": "stopped",
        "FAILED": "failed",
    }

    persisted_snapshot.update(
        {
            "status": status,
            "phase": phase,
            "task_state": task_states.get(status, "unknown"),
            "running": status in ACTIVE_STATUSES,
            "cancel_requested": cancel_requested,
            "error": error,
        }
    )

    return persisted_snapshot


# ===========================================================================
# Job claiming
# ===========================================================================


async def _claim_job(
    job_id: UUID,
    task_id: str,
) -> dict[str, Any] | None:
    """
    Claim a queued persistent job.

    Redelivered tasks may reclaim an active job only when the persisted
    Celery task ID matches. A re-execution starts preparation again; it
    does not resume a simulation from an execution checkpoint.
    """

    async with SessionLocal() as session:
        result = await session.execute(
            select(BacktestJob).where(BacktestJob.id == job_id).with_for_update()
        )
        job = result.scalar_one_or_none()

        if job is None:
            logger.error(
                "Backtest job does not exist: job_id=%s",
                job_id,
            )
            return None

        if job.status in TERMINAL_STATUSES:
            logger.info(
                "Ignoring duplicate task for terminal backtest: " "job_id=%s status=%s",
                job_id,
                job.status,
            )
            return None

        if job.celery_task_id and job.celery_task_id != task_id:
            logger.warning(
                "Backtest task ID mismatch: job_id=%s expected=%s received=%s",
                job_id,
                job.celery_task_id,
                task_id,
            )
            return None

        is_waiting_in_queue = (
            job.status == "QUEUED" and str(job.phase or "").upper() == "QUEUED"
        )

        is_redelivery = (
            job.status
            in {
                "QUEUED",
                "BACKTEST_CREATED",
                "RUNNING",
                "PREPARING",
            }
            and job.celery_task_id == task_id
        )

        if not is_waiting_in_queue and not is_redelivery:
            logger.warning(
                "Backtest task cannot claim job: job_id=%s status=%s phase=%s",
                job_id,
                job.status,
                job.phase,
            )
            return None

        if job.cancel_requested:
            BacktestJobService._apply_state(
                job,
                status="STOPPED",
                phase="STOPPED",
                task_state="stopped",
                running=False,
            )

            await session.commit()

            return None

        job.started_at = job.started_at or _utc_now()
        job.completed_at = None
        job.error = None

        # Preparation is internal progress. The public lifecycle remains
        # QUEUED until the BacktestService runtime has been created.
        BacktestJobService._apply_state(
            job,
            status="QUEUED",
            phase="PREPARING_BACKTEST_RUNTIME",
            task_state="running",
            running=True,
        )

        payload = {
            "job_id": job.id,
            "user_id": job.user_id,
            "account_id": job.account_id,
            "initial_balance": job.initial_balance,
            "start": _normalize_datetime(job.start),
            "end": _normalize_datetime(job.end),
            "close_positions_at_end": job.close_positions_at_end,
        }

        await session.commit()

        return payload


# ===========================================================================
# Job control
# ===========================================================================


async def _read_job_control(
    job_id: UUID,
) -> tuple[str | None, bool]:
    """Read the current persistent status and cancellation flag."""

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                BacktestJob.status,
                BacktestJob.cancel_requested,
            ).where(
                BacktestJob.id == job_id,
            )
        )

        row = result.one_or_none()

        if row is None:
            return None, True

        return row.status, bool(row.cancel_requested)


# ===========================================================================
# Persist lifecycle and runtime snapshots
# ===========================================================================


async def _persist_state(
    job_id: UUID,
    *,
    status: str,
    phase: str,
    snapshot: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """
    Persist a lifecycle transition and its latest runtime snapshot.

    The database row is locked while it is updated. Once terminal, a job
    cannot be overwritten by a subsequent nonterminal update from a worker.
    """

    async with SessionLocal() as session:
        result = await session.execute(
            select(BacktestJob).where(BacktestJob.id == job_id).with_for_update()
        )
        job = result.scalar_one_or_none()

        if job is None:
            raise RuntimeError(f"Backtest job {job_id} disappeared while executing.")

        # Protect terminal states from delayed updates or duplicate workers.
        if job.status in TERMINAL_STATUSES:
            await session.rollback()
            return

        if status not in {
            "QUEUED",
            "BACKTEST_CREATED",
            "RUNNING",
            "COMPLETED",
            "STOPPED",
            "FAILED",
        }:
            raise ValueError(f"Unsupported persistent backtest status: {status!r}")

        persisted_snapshot = _merge_snapshot(
            job.snapshot,
            snapshot,
            status=status,
            phase=phase,
            cancel_requested=bool(job.cancel_requested),
            error=error,
        )

        job.status = status
        job.phase = phase
        job.error = error
        job.snapshot = persisted_snapshot

        if status in TERMINAL_STATUSES:
            if job.completed_at is None:
                job.completed_at = _utc_now()

        await session.commit()


# ===========================================================================
# Backtest execution
# ===========================================================================


async def _execute_backtest_job(
    job_id: UUID,
    task_id: str,
) -> dict[str, str]:
    """Prepare, run, and persist one backtest outside the API process."""

    payload = await _claim_job(job_id, task_id)

    if payload is None:
        return {
            "backtest_id": str(job_id),
            "status": "IGNORED",
        }

    config = BacktestConfig(
        account_id=payload["account_id"],
        initial_balance=Decimal(str(payload["initial_balance"])),
        symbols=(),
        timeframes=(),
        start=payload["start"],
        end=payload["end"],
        contract_sizes={},
        close_positions_at_end=payload["close_positions_at_end"],
        user_id=payload["user_id"],
    )

    # Each Celery execution owns its runtime service and asyncio event loop.
    runtime_service = create_backtest_service()

    creation_task = asyncio.create_task(
        runtime_service.create(config),
        name=f"aqe-backtest-prepare-{job_id}",
    )

    runtime_backtest_id: UUID | None = None

    try:
        # Runtime creation may include slow historical-data preparation.
        # Poll cancellation while it is being prepared.
        while not creation_task.done():
            done, _ = await asyncio.wait(
                {creation_task},
                timeout=POLL_INTERVAL_SECONDS,
            )

            if done:
                break

            _, cancel_requested = await _read_job_control(job_id)

            if cancel_requested:
                creation_task.cancel()

                await asyncio.gather(
                    creation_task,
                    return_exceptions=True,
                )

                await _persist_state(
                    job_id,
                    status="STOPPED",
                    phase="STOPPED",
                )

                return {
                    "backtest_id": str(job_id),
                    "status": "STOPPED",
                }

        # ------------------------------------------------------------------
        # Stage 2: Runtime creation
        # ------------------------------------------------------------------

        created_snapshot = await creation_task

        if not isinstance(created_snapshot, dict):
            raise RuntimeError("BacktestService.create() did not return a snapshot.")

        runtime_id_value = created_snapshot.get("backtest_id")

        if not runtime_id_value:
            raise RuntimeError(
                "Created backtest runtime did not provide a backtest_id."
            )

        runtime_backtest_id = UUID(str(runtime_id_value))

        # Persist BACKTEST_CREATED only after runtime creation actually
        # succeeds and its runtime ID is available.
        await _persist_state(
            job_id,
            status="BACKTEST_CREATED",
            phase="BACKTEST_CREATED",
            snapshot=created_snapshot,
        )

        _, cancel_requested = await _read_job_control(job_id)

        if cancel_requested:
            await _persist_state(
                job_id,
                status="STOPPED",
                phase="STOPPED",
                snapshot=created_snapshot,
            )

            return {
                "backtest_id": str(job_id),
                "status": "STOPPED",
            }

        # ------------------------------------------------------------------
        # Stage 3: Runtime startup
        # ------------------------------------------------------------------

        # Start the runtime exactly once. Do not publish RUNNING until the
        # runtime service confirms that start() has returned successfully.
        start_result = await runtime_service.start(runtime_backtest_id)

        running_snapshot = (
            start_result if isinstance(start_result, dict) else created_snapshot
        )

        # Persist RUNNING immediately after startup. This ensures that even
        # very short backtests record the RUNNING transition before polling.
        await _persist_state(
            job_id,
            status="RUNNING",
            phase="SIMULATING",
            snapshot=running_snapshot,
        )

        stop_requested = False

        # ------------------------------------------------------------------
        # Poll runtime until it really reaches a terminal state
        # ------------------------------------------------------------------

        while True:
            _, cancel_requested = await _read_job_control(job_id)

            if cancel_requested and not stop_requested:
                await runtime_service.stop(runtime_backtest_id)
                stop_requested = True

            runtime_snapshot = await runtime_service.get(runtime_backtest_id)

            if not isinstance(runtime_snapshot, dict):
                raise RuntimeError("BacktestService.get() did not return a snapshot.")

            runtime_status = (
                str(runtime_snapshot.get("status", "RUNNING")).strip().upper()
            )

            runtime_task_state = (
                str(runtime_snapshot.get("task_state", "running")).strip().upper()
            )

            runtime_is_terminal = runtime_status in RUNTIME_TERMINAL_STATUSES

            runtime_task_finished = (
                runtime_task_state in TERMINAL_TASK_STATES
                or runtime_snapshot.get("running") is False
            )

            # A terminal runtime status can briefly precede final completion
            # of its task. Do not persist COMPLETED/STOPPED/FAILED until the
            # runtime confirms that its task has finished.
            if runtime_is_terminal and runtime_task_finished:
                await _persist_state(
                    job_id,
                    status=runtime_status,
                    phase=runtime_status,
                    snapshot=runtime_snapshot,
                    error=runtime_snapshot.get("error"),
                )

                return {
                    "backtest_id": str(job_id),
                    "status": runtime_status,
                }

            # Internal phases may change without adding lifecycle statuses.
            if runtime_is_terminal:
                if runtime_status == "STOPPED":
                    phase = "STOPPING"
                elif runtime_status == "FAILED":
                    phase = "FINALIZING_FAILURE"
                else:
                    phase = "FINALIZING"
            elif stop_requested or cancel_requested:
                phase = "STOPPING"
            else:
                phase = "SIMULATING"

            await _persist_state(
                job_id,
                status="RUNNING",
                phase=phase,
                snapshot=runtime_snapshot,
                error=runtime_snapshot.get("error"),
            )

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        # Clean up the preparation coroutine if the Celery task itself
        # is cancelled. A subsequent delivery may re-run preparation.
        if not creation_task.done():
            creation_task.cancel()

            await asyncio.gather(
                creation_task,
                return_exceptions=True,
            )

        raise

    except Exception as exc:
        logger.exception(
            "Backtest job execution failed: job_id=%s runtime_id=%s",
            job_id,
            runtime_backtest_id,
        )

        await _persist_state(
            job_id,
            status="FAILED",
            phase="FAILED",
            error=f"{type(exc).__name__}: {exc}",
        )

        raise


# ===========================================================================
# Celery entry point
# ===========================================================================


@celery_app.task(
    bind=True,
    name="aqe.backtests.execute",
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def execute_backtest_job(
    self,
    backtest_id: str,
) -> dict[str, str]:
    """
    Run one durable backtest job.

    The Celery task ID is expected to equal the persistent backtest job ID.
    """

    job_id = UUID(backtest_id)
    task_id = str(self.request.id or backtest_id)

    return asyncio.run(
        _execute_backtest_job(
            job_id,
            task_id,
        )
    )
