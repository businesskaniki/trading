
"""Database model for AQE strategy configurations and execution runs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class StrategyRun(UUIDMixin, TimestampMixin, Base):
    """
    Persisted strategy assignment, configuration, and execution record.

    A StrategyRun represents a strategy instance assigned to a specific
    trading account.

    Strategy architecture
    ---------------------
    ``StrategyDefinition`` represents the strategy implementation that
    exists in the AQE codebase and is synchronized into the strategy
    catalog.

    ``StrategyRun`` represents an account-specific configuration and
    execution record for that strategy.

    Therefore:

        StrategyDefinition
            = what strategy exists

        StrategyRun
            = how/where that strategy is configured and run

    The strategy implementation itself remains in the Strategy Engine
    registry. StrategyRun does not contain Python strategy logic.

    Symbol ownership
    ----------------
    ``AccountSymbol`` is the source of truth for the symbols available
    to an account.

    ``symbols`` is retained as a persisted configuration/history
    snapshot, but the live/backtest runtime should resolve the current
    enabled account symbols from AccountSymbol rather than treating
    this JSON field as the authoritative trading universe.
    """

    __tablename__ = "strategy_runs"

    __table_args__ = (
        Index(
            "ix_strategy_name",
            "strategy_name",
        ),
        Index(
            "ix_strategy_status",
            "status",
        ),
        Index(
            "ix_strategy_type",
            "run_type",
        ),
        Index(
            "ix_strategy_started",
            "started_at",
        ),
        Index(
            "ix_strategy_account",
            "account_id",
        ),
        Index(
            "ix_strategy_account_enabled",
            "account_id",
            "enabled",
        ),
        Index(
            "ix_strategy_definition",
            "strategy_definition_id",
        ),
        Index(
            "ix_strategy_account_definition",
            "account_id",
            "strategy_definition_id",
        ),
    )

    # ------------------------------------------------------------------
    # OWNERSHIP
    # ------------------------------------------------------------------

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="strategy_runs",
    )

    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trading_accounts.id"),
        nullable=True,
    )

    account = relationship(
        "TradingAccount",
        back_populates="strategy_runs",
    )

    # ------------------------------------------------------------------
    # STRATEGY DEFINITION
    # ------------------------------------------------------------------

    strategy_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "strategy_definitions.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    strategy_definition = relationship(
        "StrategyDefinition",
        back_populates="strategy_runs",
    )

    # ------------------------------------------------------------------
    # STRATEGY IDENTITY SNAPSHOT
    # ------------------------------------------------------------------

    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    strategy_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # USER / ACCOUNT CONFIGURATION
    # ------------------------------------------------------------------

    run_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    run_type: Mapped[StrategyRunType] = mapped_column(
        Enum(
            StrategyRunType,
            name="strategy_run_type_enum",
        ),
        nullable=False,
    )

    status: Mapped[StrategyRunStatus] = mapped_column(
        Enum(
            StrategyRunStatus,
            name="strategy_run_status_enum",
        ),
        default=StrategyRunStatus.CREATED,
        nullable=False,
    )

    # ------------------------------------------------------------------
    # STRATEGY PARAMETERS
    # ------------------------------------------------------------------

    parameters: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # ------------------------------------------------------------------
    # SYMBOL / TIMEFRAME CONFIGURATION SNAPSHOT
    # ------------------------------------------------------------------

    symbols: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # EXECUTION STATISTICS
    # ------------------------------------------------------------------

    total_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    winning_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    losing_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    net_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    profit_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    sharpe_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    expectancy: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # PERFORMANCE
    # ------------------------------------------------------------------

    performance = relationship(
        "Performance",
        back_populates="strategy_run",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # REPRESENTATION
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<StrategyRun("
            f"name='{self.strategy_name}', "
            f"version='{self.strategy_version}', "
            f"account_id='{self.account_id}', "
            f"definition_id='{self.strategy_definition_id}', "
            f"type='{self.run_type}', "
            f"status='{self.status}', "
            f"enabled={self.enabled})>"
        )
