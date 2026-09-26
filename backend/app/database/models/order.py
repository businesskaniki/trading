from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import OrderSide, OrderStatus, OrderType
from app.database.base import Base, TimestampMixin, UUIDMixin


class Order(UUIDMixin, TimestampMixin, Base):
    """
    Persisted AQE order.

    Broker identifiers are intentionally stored separately:

        broker_order_id
            Broker order/ticket created by order submission.

        broker_deal_id
            Broker execution/deal identifier.

        broker_position_id
            Broker position created by the execution, when applicable.

    execution_correlation_id
        AQE-generated deterministic identifier linking the persisted
        order to the execution decision that created it.

        This identifier is independent of broker-facing identifiers
        and must be used as the primary AQE execution correlation key.
    """

    __tablename__ = "orders"

    __table_args__ = (
        Index("ix_orders_execution_correlation_id", "execution_correlation_id"),
        Index("ix_orders_broker_order_id", "broker_order_id"),
        Index("ix_orders_broker_deal_id", "broker_deal_id"),
        Index("ix_orders_broker_position_id", "broker_position_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_strategy", "strategy"),
        Index("ix_orders_account_id", "account_id"),
        Index("ix_orders_symbol_id", "symbol_id"),
    )

    # ------------------------------------------------------------------
    # Execution correlation
    # ------------------------------------------------------------------

    execution_correlation_id: Mapped[UUID] = mapped_column(
        nullable=False,
        unique=True,
    )

    # ------------------------------------------------------------------
    # Broker identifiers
    # ------------------------------------------------------------------

    broker_order_id: Mapped[int | None] = mapped_column(
        nullable=True,
        unique=True,
    )

    broker_deal_id: Mapped[int | None] = mapped_column(
        nullable=True,
        unique=True,
    )

    broker_position_id: Mapped[int | None] = mapped_column(
        nullable=True,
        unique=True,
    )

    # ------------------------------------------------------------------
    # Order ownership / strategy
    # ------------------------------------------------------------------

    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id"),
        nullable=False,
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id"),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

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
    # Order definition
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    requested_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
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
    # Lifecycle
    # ------------------------------------------------------------------

    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status_enum",
        ),
        default=OrderStatus.CREATED,
        nullable=False,
    )