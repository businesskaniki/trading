from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import OrderSide, OrderStatus, OrderType
from app.database.base import Base, TimestampMixin, UUIDMixin


class Order(UUIDMixin, TimestampMixin, Base):
    """
    Represents an order submitted through AQE.

    The Order model stores the persistent AQE representation
    of an order and its broker execution information.
    """

    __tablename__ = "orders"

    __table_args__ = (
        Index("ix_orders_ticket", "ticket"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_strategy", "strategy"),
        Index("ix_orders_account_id", "account_id"),
        Index("ix_orders_symbol_id", "symbol_id"),
    )

    # ==========================================================
    # BROKER INFORMATION
    # ==========================================================

    ticket: Mapped[int | None] = mapped_column(
        nullable=True,
        unique=True,
    )

    # ==========================================================
    # ORDER OWNERSHIP / SOURCE
    # ==========================================================

    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # ACCOUNT / SYMBOL
    # ==========================================================

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

    # ==========================================================
    # ORDER DETAILS
    # ==========================================================

    order_type: Mapped[OrderType] = mapped_column(
        Enum(
            OrderType,
            name="order_type_enum",
        ),
        nullable=False,
    )

    side: Mapped[OrderSide] = mapped_column(
        Enum(
            OrderSide,
            name="order_side_enum",
        ),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # ----------------------------------------------------------
    # Requested price
    # ----------------------------------------------------------
    #
    # MARKET orders do not necessarily have a requested price.
    #
    # LIMIT / STOP orders require one.
    #
    # ----------------------------------------------------------

    requested_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    # ----------------------------------------------------------
    # Actual broker execution price
    # ----------------------------------------------------------

    executed_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    # ----------------------------------------------------------
    # Risk parameters
    # ----------------------------------------------------------

    stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    take_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    # ==========================================================
    # STATUS
    # ==========================================================

    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status_enum",
        ),
        default=OrderStatus.CREATED,
        nullable=False,
    )

    # ==========================================================
    # REPRESENTATION
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<Order("
            f"id={self.id}, "
            f"ticket={self.ticket}, "
            f"symbol={self.symbol_id}, "
            f"side={self.side}, "
            f"volume={self.volume}, "
            f"status={self.status})>"
        )