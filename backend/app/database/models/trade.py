from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PositionDirection, TradeResult
from app.database.base import Base, TimestampMixin, UUIDMixin


class Trade(UUIDMixin, TimestampMixin, Base):
    """
    Immutable record of a completed trade.

    A Trade is created only after a Position has been completely closed.
    """

    __tablename__ = "trades"

    __table_args__ = (
        Index("ix_trade_ticket", "ticket"),
        Index("ix_trade_strategy", "strategy"),
        Index("ix_trade_symbol", "symbol_id"),
        Index("ix_trade_account", "account_id"),
        Index("ix_trade_opened", "opened_at"),
        Index("ix_trade_closed", "closed_at"),
    )

    # ==========================================================
    # BROKER INFORMATION
    # ==========================================================

    ticket: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
    )

    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # ==========================================================
    # RELATIONSHIPS
    # ==========================================================

    position_id: Mapped[UUID] = mapped_column(
        ForeignKey("positions.id"),
        unique=True,
        nullable=False,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id"),
        nullable=False,
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id"),
        nullable=False,
    )

    position = relationship(
        "Position",
        back_populates="trade",
    )

    account = relationship(
        "TradingAccount",
        back_populates="trades",
    )

    symbol = relationship(
        "Symbol",
        back_populates="trades",
    )

    # ==========================================================
    # TRADE DETAILS
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

    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    exit_price: Mapped[Decimal] = mapped_column(
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
    # PROFIT
    # ==========================================================

    gross_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    swap: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )

    net_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    profit_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # ==========================================================
    # RISK STATISTICS
    # ==========================================================

    initial_risk: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    reward_risk_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    max_favorable_excursion: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    max_adverse_excursion: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    # ==========================================================
    # CLASSIFICATION
    # ==========================================================

    result: Mapped[TradeResult] = mapped_column(
        Enum(
            TradeResult,
            name="trade_result_enum",
        ),
        nullable=False,
    )

    # ==========================================================
    # LIFECYCLE
    # ==========================================================

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    duration_seconds: Mapped[int] = mapped_column(
        Integer,
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
            f"<Trade("
            f"id={self.id}, "
            f"ticket={self.ticket}, "
            f"strategy='{self.strategy}', "
            f"net_profit={self.net_profit}, "
            f"result={self.result})>"
        )