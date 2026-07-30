from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.database.models.base import TimestampMixin, UUIDMixin

from app.core.constants import AssetClass


class Symbol(UUIDMixin, TimestampMixin, Base):
    """
    Tradable financial instrument.

    Examples:
        - BTCUSD
        - XAUUSD
        - EURUSD
        - US100
    """

    __tablename__ = "symbols"

    __table_args__ = (
        Index("ix_symbols_name", "name"),
        Index("ix_symbols_asset_class", "asset_class"),
    )

    # ------------------------------------------------------------------
    # Basic Information
    # ------------------------------------------------------------------

    name: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    broker_symbol: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    asset_class: Mapped[AssetClass] = mapped_column(
        SQLEnum(
            AssetClass,
            name="asset_class_enum",
        ),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Trading Specifications
    # ------------------------------------------------------------------

    digits: Mapped[int] = mapped_column(
        default=5,
        nullable=False,
    )

    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    contract_size: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("100000"),
        nullable=False,
    )

    min_volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.01"),
        nullable=False,
    )

    max_volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("100.00"),
        nullable=False,
    )

    volume_step: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.01"),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    orders: Mapped[list["Order"]] = relationship(
        back_populates="symbol",
        lazy="selectin",
    )

    positions: Mapped[list["Position"]] = relationship(
        back_populates="symbol",
        lazy="selectin",
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="symbol",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<Symbol("
            f"name='{self.name}', "
            f"asset_class='{self.asset_class.value}'"
            f")>"
        )