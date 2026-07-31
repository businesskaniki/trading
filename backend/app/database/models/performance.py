from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.core.constants import PerformancePeriod
from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin



class Performance(UUIDMixin, TimestampMixin, Base):
    """
    Performance statistics generated for a strategy run.

    These are snapshot values used by dashboards,
    reports and analytics.
    """

    __tablename__ = "performance"

    __table_args__ = (
        Index("ix_performance_period", "period"),
        Index("ix_performance_created", "created_at"),
    )

    # ==========================================================
    # Relationship
    # ==========================================================

    strategy_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    strategy_run = relationship(
        "StrategyRun",
        back_populates="performance",
    )

    # ==========================================================
    # Classification
    # ==========================================================

    period: Mapped[PerformancePeriod] = mapped_column(
        Enum(
            PerformancePeriod,
            name="performance_period_enum",
        ),
        nullable=False,
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ==========================================================
    # Trade Statistics
    # ==========================================================

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

    breakeven_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Financial Metrics
    # ==========================================================

    gross_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    gross_loss: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    net_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    total_commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    total_swap: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Performance Ratios
    # ==========================================================

    win_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=0,
        nullable=False,
    )

    profit_factor: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    expectancy: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    sharpe_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    sortino_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    calmar_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # ==========================================================
    # Drawdown
    # ==========================================================

    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    max_drawdown_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Risk Metrics
    # ==========================================================

    average_r_multiple: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    recovery_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    payoff_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # ==========================================================
    # Holding Statistics
    # ==========================================================

    average_trade_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    average_win: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    average_loss: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    largest_win: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    largest_loss: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Equity
    # ==========================================================

    starting_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    ending_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    peak_equity: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    lowest_equity: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self):
        return (
            f"<Performance("
            f"period={self.period}, "
            f"net_profit={self.net_profit}, "
            f"win_rate={self.win_rate})>"
        )