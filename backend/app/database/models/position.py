from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PositionDirection, PositionStatus
from app.database.base import Base, TimestampMixin, UUIDMixin


class Position(UUIDMixin, TimestampMixin, Base):
    """
    Represents an active or previously active market position.

    A Position is the persistent AQE representation of broker
    position state.
    """

    __tablename__ = "positions"

    __table_args__ = (
        Index("ix_positions_ticket", "ticket"),
        Index("ix_positions_status", "status"),
        Index("ix_positions_symbol", "symbol_id"),
        Index("ix_positions_account", "account_id"),
        Index("ix_positions_order", "order_id"),
    )

    # ==========================================================
    # BROKER INFORMATION
    # ==========================================================

    ticket: Mapped[int] = mapped_column(
        unique=True,
        nullable=False,
    )

    broker_position_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # ==========================================================
    # RELATIONSHIPS
    # ==========================================================

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id"),
        nullable=False,
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id"),
        nullable=False,
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )

    account = relationship(
        "TradingAccount",
        back_populates="positions",
    )

    symbol = relationship(
        "Symbol",
        back_populates="positions",
    )

    order = relationship(
        "Order",
        back_populates="position",
    )

    trade = relationship(
        "Trade",
        back_populates="position",
        uselist=False,
    )

    # ==========================================================
    # POSITION DETAILS
    # ==========================================================

    direction: Mapped[PositionDirection] = mapped_column(
        Enum(
            PositionDirection,
            name="position_direction_enum",
        ),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    current_volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    current_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    take_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    # ==========================================================
    # PROFIT METRICS
    # ==========================================================

    floating_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    swap: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    # ==========================================================
    # RISK
    # ==========================================================

    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    initial_risk: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    # ==========================================================
    # STATUS
    # ==========================================================

    status: Mapped[PositionStatus] = mapped_column(
        Enum(
            PositionStatus,
            name="position_status_enum",
        ),
        default=PositionStatus.OPEN,
        nullable=False,
    )

    # ==========================================================
    # LIFECYCLE
    # ==========================================================

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_updated_price_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # MANAGEMENT FLAGS
    # ==========================================================

    break_even_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    trailing_stop_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # ==========================================================
    # NOTES
    # ==========================================================

    comment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # REPRESENTATION
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<Position("
            f"id={self.id}, "
            f"ticket={self.ticket}, "
            f"symbol={self.symbol_id}, "
            f"direction={self.direction}, "
            f"status={self.status})>"
        )