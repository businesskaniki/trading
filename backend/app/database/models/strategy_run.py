from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


from app.core.constants import StrategyRunStatus
from app.core.constants import StrategyRunType
from app.database.models.base import Base
from app.database.models.base import TimestampMixin
from app.database.models.base import UUIDMixin


class StrategyRun(UUIDMixin, TimestampMixin, Base):
    """
    Represents one execution of a trading strategy.

    A strategy can have many runs:
    - Backtesting
    - Paper Trading
    - Live Trading
    """

    __tablename__ = "strategy_runs"

    __table_args__ = (
        Index("ix_strategy_name", "strategy_name"),
        Index("ix_strategy_status", "status"),
        Index("ix_strategy_type", "run_type"),
        Index("ix_strategy_started", "started_at"),
    )

    # ==========================================================
    # Strategy Information
    # ==========================================================

    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    strategy_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    run_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Execution
    # ==========================================================

    run_type: Mapped[StrategyRunType] = mapped_column(
        Enum(StrategyRunType, name="strategy_run_type_enum"),
        nullable=False,
    )

    status: Mapped[StrategyRunStatus] = mapped_column(
        Enum(StrategyRunStatus, name="strategy_run_status_enum"),
        default=StrategyRunStatus.CREATED,
        nullable=False,
    )

    # ==========================================================
    # Configuration
    # ==========================================================

    parameters: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    symbols: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # ==========================================================
    # Statistics
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
    performance = relationship(
    "Performance",
    back_populates="strategy_run",
    uselist=False,
    cascade="all, delete-orphan",
)
    # ==========================================================
    # Timing
    # ==========================================================

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Notes
    # ==========================================================

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<StrategyRun("
            f"name='{self.strategy_name}', "
            f"version='{self.strategy_version}', "
            f"type='{self.run_type}', "
            f"status='{self.status}')>"
        )