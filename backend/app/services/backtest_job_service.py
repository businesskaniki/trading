"""Persistent application service for AQE backtest jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.backtest_job import BacktestJob

# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------

LIFECYCLE_STATUSES = frozenset(
    {
        "QUEUED",
        "BACKTEST_CREATED",
        "RUNNING",
        "COMPLETED",
        "STOPPED",
        "FAILED",
    }
)

ACTIVE_STATUSES = frozenset(
    {
        "QUEUED",
        "BACKTEST_CREATED",
        "RUNNING",
        # Legacy states retained for jobs created by the previous version.
        "PREPARING",
        "STARTING",
        "IN_PROGRESS",
    }
)

TERMINAL_STATUSES = frozenset(
    {
        "COMPLETED",
        "STOPPED",
        "FAILED",
    }
)


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def canonical_backtest_status(
    status: str | None,
    phase: str | None = None,
) -> str:
    """Map internal and legacy states to the public lifecycle."""

    normalized_status = str(status or "UNKNOWN").strip().upper()
    normalized_phase = str(phase or "").strip().upper()

    if normalized_status == "PREPARING":
        if normalized_phase in {
            "BACKTEST_CREATED",
            "RUNTIME_CREATED",
            "STARTING_SIMULATION",
        }:
            return "BACKTEST_CREATED"

        return "QUEUED"

    if normalized_status == "STARTING":
        return "BACKTEST_CREATED"

    if normalized_status == "IN_PROGRESS":
        return "RUNNING"

    return normalized_status


def append_backtest_status_history(
    snapshot: dict[str, Any] | None,
    *,
    status: str,
    phase: str,
) -> dict[str, Any]:
    """
    Preserve observed lifecycle transitions in the persisted snapshot.

    Internal phase updates do not create duplicate lifecycle entries.
    This function records transitions that the backend actually observes;
    it does not invent missing historical stages.
    """

    result = dict(snapshot or {})
    existing_history = result.get("status_history")

    if isinstance(existing_history, list):
        history = [dict(entry) for entry in existing_history if isinstance(entry, dict)]
    else:
        history = []

    result["status_history"] = history

    public_status = canonical_backtest_status(status, phase)

    if public_status not in LIFECYCLE_STATUSES:
        return result

    previous_status = history[-1].get("status") if history else None

    if previous_status != public_status:
        history.append(
            {
                "status": public_status,
                "phase": str(phase or public_status).strip().upper(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    return result


def _safe_count(value: Any) -> int:
    """Convert a supported count or collection into a non-negative integer."""

    if isinstance(value, (list, tuple)):
        return len(value)

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


# ---------------------------------------------------------------------------
# Persistent backtest job service
# ---------------------------------------------------------------------------


class BacktestJobService:
    """Database operations and API snapshots for persistent backtest jobs."""

    # =======================================================================
    # Initial snapshot
    # =======================================================================

    @staticmethod
    def initial_snapshot(job: BacktestJob) -> dict[str, Any]:
        """Build the initial response using the existing frontend contract."""

        balance = str(job.initial_balance)

        return {
            "backtest_id": str(job.id),
            "status": canonical_backtest_status(job.status, job.phase),
            "phase": job.phase,
            "task_state": "not_started",
            "running": False,
            "cancel_requested": bool(job.cancel_requested),
            "status_history": [],
            "outcome": None,
            "outcome_message": None,
            "config": {
                "account_id": str(job.account_id),
                "initial_balance": balance,
                "start": job.start.isoformat(),
                "end": job.end.isoformat(),
                "close_positions_at_end": job.close_positions_at_end,
                "symbols": [],
                "timeframes": [],
                "contract_sizes": {},
            },
            "run": {
                "started_at": None,
                "completed_at": None,
                "current_time": None,
                "processed_events": 0,
                "processed_candles": 0,
                "executions": 0,
                "pending_orders": 0,
                "errors": [],
            },
            "portfolio": {
                "balance": balance,
                "equity": balance,
                "realized_pnl": "0",
                "unrealized_pnl": "0",
            },
            "orchestration": None,
            "error": None,
        }

    # =======================================================================
    # API serialization
    # =======================================================================

    @classmethod
    def serialize(cls, job: BacktestJob) -> dict[str, Any]:
        """Return the persisted snapshot with authoritative lifecycle fields."""

        if job.snapshot is not None:
            snapshot = dict(job.snapshot)
        else:
            snapshot = cls.initial_snapshot(job)

        initial = cls.initial_snapshot(job)

        if not isinstance(snapshot.get("config"), dict):
            snapshot["config"] = initial["config"]

        existing_history = snapshot.get("status_history")

        if isinstance(existing_history, list):
            status_history = [
                dict(entry) for entry in existing_history if isinstance(entry, dict)
            ]
        else:
            status_history = []

        public_status = canonical_backtest_status(
            job.status,
            job.phase,
        )

        snapshot.update(
            {
                "backtest_id": str(job.id),
                "status": public_status,
                "phase": job.phase,
                "cancel_requested": bool(job.cancel_requested),
                "running": public_status in ACTIVE_STATUSES,
                "status_history": status_history,
                "error": job.error,
            }
        )

        snapshot["task_state"] = cls._resolve_task_state(
            raw_status=job.status,
            phase=job.phase,
            public_status=public_status,
        )

        if public_status == "COMPLETED":
            outcome, outcome_message = cls._derive_outcome(snapshot)
            snapshot["outcome"] = outcome
            snapshot["outcome_message"] = outcome_message
        else:
            snapshot["outcome"] = None
            snapshot["outcome_message"] = None

        return snapshot

    @staticmethod
    def _resolve_task_state(
        *,
        raw_status: str,
        phase: str | None,
        public_status: str,
    ) -> str:
        """Resolve the task state consistently for the frontend."""

        normalized_raw = str(raw_status or "").strip().upper()
        normalized_phase = str(phase or "").strip().upper()

        if public_status == "CREATED":
            return "not_started"

        if public_status == "QUEUED":
            if normalized_raw == "QUEUED" and normalized_phase == "QUEUED":
                return "queued"

            # The worker may be preparing the runtime while the public
            # lifecycle status remains QUEUED.
            return "running"

        if public_status in {"BACKTEST_CREATED", "RUNNING"}:
            return "running"

        if public_status == "COMPLETED":
            return "completed"

        if public_status == "STOPPED":
            return "stopped"

        if public_status == "FAILED":
            return "failed"

        if normalized_raw in ACTIVE_STATUSES:
            return "running"

        return "unknown"

    @staticmethod
    def _derive_outcome(
        snapshot: dict[str, Any],
    ) -> tuple[str, str]:
        """
        Classify the results of a completed backtest.

        COMPLETED describes the simulation lifecycle. This outcome separately
        reports whether the run processed data, generated signals, or executed
        trades. A completed run with no trades is not automatically a failure.
        """

        run = snapshot.get("run")
        if not isinstance(run, dict):
            run = {}

        orchestration = snapshot.get("orchestration")
        if not isinstance(orchestration, dict):
            orchestration = {}

        strategy_results = orchestration.get("strategy_results")
        if not isinstance(strategy_results, dict):
            strategy_results = {}

        processed_events = max(
            _safe_count(run.get("processed_events")),
            _safe_count(run.get("processed_candles")),
        )

        top_level_signals = _safe_count(orchestration.get("signals_received"))

        attributed_signals = sum(
            _safe_count(result.get("signals_received"))
            for result in strategy_results.values()
            if isinstance(result, dict)
        )

        signal_count = max(
            top_level_signals,
            attributed_signals,
        )

        run_executions = _safe_count(run.get("executions"))
        orchestration_executions = _safe_count(orchestration.get("executions"))

        execution_count = max(
            run_executions,
            orchestration_executions,
        )

        if execution_count > 0:
            return (
                "TRADES_EXECUTED",
                f"Backtest completed with {execution_count} execution(s).",
            )

        if signal_count > 0:
            return (
                "NO_EXECUTIONS",
                (
                    "Backtest completed. Strategy signals were generated, "
                    "but no executions occurred."
                ),
            )

        if processed_events > 0:
            return (
                "NO_SIGNALS",
                (
                    f"Backtest completed after processing {processed_events} "
                    "market event(s), but no strategy signals were generated. "
                    "No executions occurred."
                ),
            )

        return (
            "NO_MARKET_EVENTS",
            "Backtest completed without processing market events.",
        )

    # =======================================================================
    # State updates
    # =======================================================================

    @staticmethod
    def _apply_state(
        job: BacktestJob,
        *,
        status: str,
        phase: str,
        task_state: str,
        running: bool,
        error: str | None = None,
    ) -> None:
        """Update lifecycle columns and the embedded API snapshot together."""

        if job.snapshot is not None:
            snapshot = dict(job.snapshot)
        else:
            snapshot = BacktestJobService.initial_snapshot(job)

        normalized_phase = str(phase or status).strip().upper()

        public_status = canonical_backtest_status(
            status,
            normalized_phase,
        )

        snapshot = append_backtest_status_history(
            snapshot,
            status=public_status,
            phase=normalized_phase,
        )

        effective_running = bool(running and public_status in ACTIVE_STATUSES)

        snapshot.update(
            {
                "backtest_id": str(job.id),
                "status": public_status,
                "phase": normalized_phase,
                "task_state": task_state,
                "running": effective_running,
                "cancel_requested": bool(job.cancel_requested),
                "status_history": list(snapshot.get("status_history") or []),
                "error": error,
            }
        )

        job.status = public_status
        job.phase = normalized_phase
        job.snapshot = snapshot
        job.error = error

        if public_status in TERMINAL_STATUSES and job.completed_at is None:
            job.completed_at = datetime.now(timezone.utc)

    # =======================================================================
    # Create
    # =======================================================================

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: UUID,
        account_id: UUID,
        initial_balance: Decimal,
        start: datetime,
        end: datetime,
        close_positions_at_end: bool,
    ) -> BacktestJob:
        """Persist a CREATED job without constructing the simulation runtime."""

        if start >= end:
            raise ValueError("Backtest start must be before backtest end.")

        job = BacktestJob(
            user_id=user_id,
            account_id=account_id,
            initial_balance=initial_balance,
            start=start,
            end=end,
            close_positions_at_end=close_positions_at_end,
            status="CREATED",
            phase="CREATED",
            cancel_requested=False,
        )

        db.add(job)
        await db.flush()

        job.snapshot = BacktestJobService.initial_snapshot(job)

        await db.commit()
        await db.refresh(job)

        return job

    # =======================================================================
    # Read
    # =======================================================================

    @staticmethod
    async def get_owned(
        db: AsyncSession,
        *,
        backtest_id: UUID,
        user_id: UUID,
    ) -> BacktestJob:
        """Read a job only when it belongs to the authenticated user."""

        result = await db.execute(
            select(BacktestJob).where(
                BacktestJob.id == backtest_id,
                BacktestJob.user_id == user_id,
            )
        )

        job = result.scalar_one_or_none()

        if job is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        return job

    @staticmethod
    async def list_owned(
        db: AsyncSession,
        *,
        user_id: UUID,
    ) -> list[BacktestJob]:
        """List jobs owned by a user, newest first."""

        result = await db.execute(
            select(BacktestJob)
            .where(BacktestJob.user_id == user_id)
            .order_by(
                BacktestJob.created_at.desc(),
                BacktestJob.id.desc(),
            )
        )

        return list(result.scalars().all())

    # =======================================================================
    # Queue
    # =======================================================================

    @staticmethod
    async def queue_owned(
        db: AsyncSession,
        *,
        backtest_id: UUID,
        user_id: UUID,
        celery_task_id: str,
    ) -> BacktestJob:
        """Atomically transition a CREATED job to QUEUED."""

        result = await db.execute(
            select(BacktestJob)
            .where(
                BacktestJob.id == backtest_id,
                BacktestJob.user_id == user_id,
            )
            .with_for_update()
        )

        job = result.scalar_one_or_none()

        if job is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        if job.status != "CREATED":
            raise RuntimeError(
                f"Backtest {backtest_id} cannot be started " f"from state {job.status}."
            )

        job.celery_task_id = celery_task_id
        job.cancel_requested = False

        BacktestJobService._apply_state(
            job,
            status="QUEUED",
            phase="QUEUED",
            task_state="queued",
            running=True,
        )

        await db.commit()
        await db.refresh(job)

        return job

    # =======================================================================
    # Dispatch failure
    # =======================================================================

    @staticmethod
    async def mark_enqueue_failed(
        db: AsyncSession,
        *,
        backtest_id: UUID,
        celery_task_id: str,
        error: str,
    ) -> None:
        """
        Record a dispatch failure without overwriting a task already claimed.

        The phase check matters because a worker may be preparing its runtime
        while the persisted public lifecycle status remains QUEUED.
        """

        result = await db.execute(
            select(BacktestJob).where(BacktestJob.id == backtest_id).with_for_update()
        )

        job = result.scalar_one_or_none()

        if job is None:
            return

        if (
            job.status != "QUEUED"
            or job.phase != "QUEUED"
            or job.celery_task_id != celery_task_id
        ):
            return

        BacktestJobService._apply_state(
            job,
            status="FAILED",
            phase="FAILED",
            task_state="failed",
            running=False,
            error=error,
        )

        await db.commit()

    # =======================================================================
    # Cancellation
    # =======================================================================

    @staticmethod
    async def request_stop_owned(
        db: AsyncSession,
        *,
        backtest_id: UUID,
        user_id: UUID,
    ) -> BacktestJob:
        """Request cooperative cancellation of a queued or active job."""

        result = await db.execute(
            select(BacktestJob)
            .where(
                BacktestJob.id == backtest_id,
                BacktestJob.user_id == user_id,
            )
            .with_for_update()
        )

        job = result.scalar_one_or_none()

        if job is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        if job.status == "CREATED":
            raise RuntimeError(f"Backtest {backtest_id} has not been started.")

        if job.status in TERMINAL_STATUSES:
            return job

        job.cancel_requested = True

        # Stop immediately only when the job is still waiting for a worker.
        # A job using QUEUED + PREPARING_BACKTEST_RUNTIME is already claimed
        # and must be stopped cooperatively by that worker.
        waiting_in_queue = (
            canonical_backtest_status(job.status, job.phase) == "QUEUED"
            and str(job.phase or "").strip().upper() == "QUEUED"
        )

        if waiting_in_queue:
            BacktestJobService._apply_state(
                job,
                status="STOPPED",
                phase="STOPPED",
                task_state="stopped",
                running=False,
            )
        else:
            BacktestJobService._apply_state(
                job,
                status=job.status,
                phase="CANCELLATION_REQUESTED",
                task_state="running",
                running=True,
            )

        await db.commit()
        await db.refresh(job)

        return job

    # =======================================================================
    # Delete
    # =======================================================================

    @staticmethod
    async def delete_owned(
        db: AsyncSession,
        *,
        backtest_id: UUID,
        user_id: UUID,
    ) -> None:
        """Delete a non-active job owned by the authenticated user."""

        result = await db.execute(
            select(BacktestJob)
            .where(
                BacktestJob.id == backtest_id,
                BacktestJob.user_id == user_id,
            )
            .with_for_update()
        )

        job = result.scalar_one_or_none()

        if job is None:
            raise KeyError(f"Backtest {backtest_id} was not found.")

        public_status = canonical_backtest_status(
            job.status,
            job.phase,
        )

        if public_status in ACTIVE_STATUSES:
            raise RuntimeError(
                f"Backtest {backtest_id} is still active. " "Stop it before deleting."
            )

        await db.delete(job)
        await db.commit()
