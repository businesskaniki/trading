"""Persistent lifecycle state for AQE backtest jobs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class BacktestJob(UUIDMixin, TimestampMixin, Base):
    """
    Durable record for one account-level backtest.

    PostgreSQL is the source of truth for lifecycle state and snapshots.
    Celery executes the work independently of the API process.

    The in-memory BacktestEngine remains responsible for simulation
    mechanics; this model does not duplicate the engine's calculations.
    """

    __tablename__ = "backtest_jobs"

    __table_args__ = (
        Index(
            "ix_backtest_jobs_user_created_at",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_backtest_jobs_account_created_at",
            "account_id",
            "created_at",
        ),
        Index(
            "ix_backtest_jobs_status_created_at",
            "status",
            "created_at",
        ),
    )

    # --------------------------------------------------------------
    # Ownership
    # --------------------------------------------------------------

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # --------------------------------------------------------------
    # Requested configuration
    # --------------------------------------------------------------

    initial_balance: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    close_positions_at_end: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # --------------------------------------------------------------
    # Job lifecycle
    # --------------------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(32),
        default="CREATED",
        nullable=False,
    )

    phase: Mapped[str] = mapped_column(
        String(64),
        default="CREATED",
        nullable=False,
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --------------------------------------------------------------
    # Recoverable status and results
    # --------------------------------------------------------------

    snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestJob("
            f"id={self.id}, "
            f"status={self.status}, "
            f"phase={self.phase})>"
        )
