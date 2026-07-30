from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.core.constants import OrderSide
from app.core.constants import OrderStatus
from app.core.constants import OrderType
from app.database.models.base import Base
from app.database.models.base import TimestampMixin
from app.database.models.base import UUIDMixin


class Order(UUIDMixin, TimestampMixin, Base):
    """
    Represents an order submitted to a broker.
    """

    __tablename__ = "orders"

    __table_args__ = (
        Index("ix_orders_ticket", "ticket"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_strategy", "strategy"),
    )

    # ------------------------------------------------------------------
    # Broker Information
    # ------------------------------------------------------------------

    ticket: Mapped[int | None] = mapped_column(
        unique=True,
        nullable=True,
    )

    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id"),
        nullable=False,
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id"),
        nullable=False,
    )

    account = relationship(
        "TradingAccount",
        back_populates="orders",
    )

    symbol = relationship(
        "Symbol",
        back_populates="orders",
    )

    position = relationship(
        "Position",
        back_populates="order",
        uselist=False,
    )

    # ------------------------------------------------------------------
    # Order Details
    # ------------------------------------------------------------------

    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type_enum"),
        nullable=False,
    )

    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side_enum"),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    requested_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    executed_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    take_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum"),
        default=OrderStatus.CREATED,
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<Order("
            f"ticket={self.ticket}, "
            f"symbol={self.symbol_id}, "
            f"side={self.side}, "
            f"status={self.status})>"
        )