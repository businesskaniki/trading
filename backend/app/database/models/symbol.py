from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.core.constants import AssetClass
from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class Symbol(UUIDMixin, TimestampMixin, Base):
    """
    Canonical tradable financial instrument.

    Examples:

        EURUSD
        XAUUSD
        BTCUSD
        US100

    Broker-specific symbol names and trading specifications belong
    to AccountSymbol because different trading accounts may expose
    the same instrument differently.
    """

    __tablename__ = "symbols"

    __table_args__ = (
        Index(
            "ix_symbols_name",
            "name",
        ),
        Index(
            "ix_symbols_asset_class",
            "asset_class",
        ),
        Index(
            "ix_symbols_active",
            "active",
        ),
    )

    # ==========================================================
    # Identity
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Asset Classification
    # ==========================================================

    asset_class: Mapped[AssetClass] = mapped_column(
        SQLEnum(
            AssetClass,
            name="asset_class_enum",
        ),
        nullable=False,
    )

    # ==========================================================
    # AQE Status
    # ==========================================================

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # Account-Specific Symbol Mappings
    # ==========================================================

    account_symbols = relationship(
        "AccountSymbol",
        back_populates="symbol",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ==========================================================
    # Trading Relationships
    # ==========================================================

    historical_candles: Mapped[list["HistoricalCandle"]] = relationship(
        "HistoricalCandle",
        back_populates="symbol",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="symbol",
        lazy="selectin",
    )

    positions: Mapped[list["Position"]] = relationship(
        "Position",
        back_populates="symbol",
        lazy="selectin",
    )

    trades: Mapped[list["Trade"]] = relationship(
        "Trade",
        back_populates="symbol",
        lazy="selectin",
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<Symbol("
            f"name='{self.name}', "
            f"asset_class='{self.asset_class.value}'"
            f")>"
        )
