from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.database.models.symbol import Symbol


class HistoricalCandle(UUIDMixin, TimestampMixin, Base):
    """
    Persisted historical OHLCV candle.

    Historical candles are associated with the canonical Symbol rather
    than AccountSymbol. Broker-specific symbol names are only used when
    retrieving the data from the MT5 bridge.
    """

    __tablename__ = "historical_candles"

    __table_args__ = (
        UniqueConstraint(
            "symbol_id",
            "timeframe",
            "timestamp",
            name="uq_historical_candle_symbol_timeframe_timestamp",
        ),
        Index(
            "ix_historical_candles_symbol_timeframe_timestamp",
            "symbol_id",
            "timeframe",
            "timestamp",
        ),
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "symbols.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    open: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    high: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    low: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    close: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    spread: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 10),
        nullable=True,
    )

    symbol: Mapped["Symbol"] = relationship(
        "Symbol",
        back_populates="historical_candles",
    )
