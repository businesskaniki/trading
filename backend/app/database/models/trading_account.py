from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.core.constants import AccountStatus
from app.core.constants import BrokerType
from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin



class TradingAccount(UUIDMixin, TimestampMixin, Base):
    """
    Represents a broker trading account.

    Examples:
        MT5 Demo
        MT5 Live
        Binance Futures
    """

    __tablename__ = "trading_accounts"

    __table_args__ = (
        Index("ix_account_number", "account_number"),
        Index("ix_broker", "broker"),
    )

    # ----------------------------------------------------------
    # Broker Information
    # ----------------------------------------------------------

    broker: Mapped[BrokerType] = mapped_column(
        Enum(BrokerType, name="broker_type_enum"),
        nullable=False,
    )

    account_number: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
    )

    server: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    account_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
    )

    leverage: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    # ----------------------------------------------------------
    # Account Metrics
    # ----------------------------------------------------------

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    equity: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    margin: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    free_margin: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    margin_level: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status_enum"),
        default=AccountStatus.DISCONNECTED,
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ----------------------------------------------------------
    # Relationships
    # ----------------------------------------------------------

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="trading_accounts",
    )

    orders = relationship(
        "Order",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    positions = relationship(
        "Position",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    trades = relationship(
        "Trade",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    risk_snapshots = relationship(
        "RiskSnapshot",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    risk_profile = relationship(
        "RiskProfile",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # ----------------------------------------------------------
    # Representation
    # ----------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<TradingAccount("
            f"account={self.account_number}, "
            f"broker={self.broker}, "
            f"status={self.status})>"
        )
