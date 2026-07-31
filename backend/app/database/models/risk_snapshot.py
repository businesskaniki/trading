from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.core.constants import RiskLevel
from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin



class RiskSnapshot(UUIDMixin, TimestampMixin, Base):
    """
    Stores a snapshot of portfolio risk at a point in time.

    These snapshots are used for monitoring,
    reporting and historical analysis.
    """

    __tablename__ = "risk_snapshots"

    __table_args__ = (
        Index("ix_risk_account", "account_id"),
        Index("ix_risk_level", "risk_level"),
        Index("ix_risk_timestamp", "snapshot_time"),
    )

    # ==========================================================
    # Relationship
    # ==========================================================

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trading_accounts.id",
            ondelete="CASCADE"
        ),
        nullable=False,
    )

    account = relationship(
        "TradingAccount",
        back_populates="risk_snapshots",
    )

    # ==========================================================
    # Account Snapshot
    # ==========================================================

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    equity: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    margin: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    free_margin: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    margin_level: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    # ==========================================================
    # Exposure
    # ==========================================================

    total_open_positions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_open_orders: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_volume: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    exposure: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    exposure_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Drawdown
    # ==========================================================

    floating_profit_loss: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    daily_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    daily_drawdown_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    max_drawdown_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Risk Metrics
    # ==========================================================

    value_at_risk: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    expected_shortfall: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    portfolio_heat: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    risk_per_trade: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    total_open_risk: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    correlation_risk: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Risk Status
    # ==========================================================

    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(
            RiskLevel,
            name="risk_level_enum"
        ),
        nullable=False,
    )

    daily_loss_limit_hit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    weekly_loss_limit_hit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    trading_halted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ==========================================================
    # Timestamp
    # ==========================================================

    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self):
        return (
            f"<RiskSnapshot("
            f"risk={self.risk_level}, "
            f"equity={self.equity}, "
            f"drawdown={self.daily_drawdown_percent})>"
        )