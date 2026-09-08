from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
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
    A trading account belonging to an AQE user.

    Stores the information required to identify and connect to
    the user's broker/platform account.

    Example:

        Broker:        MT5
        Login:         1200122668
        Server:        JustMarkets-Demo3
        Demo:          True

    MT5 credentials are stored encrypted in credentials_encrypted.
    Plain-text passwords must never be returned through the API.
    """

    __tablename__ = "trading_accounts"

    __table_args__ = (
        UniqueConstraint(
            "broker",
            "server",
            "login",
            name="uq_trading_account_identity",
        ),
        Index(
            "ix_trading_accounts_user_id",
            "user_id",
        ),
        Index(
            "ix_trading_accounts_broker",
            "broker",
        ),
        Index(
            "ix_trading_accounts_status",
            "status",
        ),
    )

    # ==========================================================
    # Ownership
    # ==========================================================

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="trading_accounts",
    )

    # ==========================================================
    # Broker
    # ==========================================================

    broker: Mapped[BrokerType] = mapped_column(
        Enum(
            BrokerType,
            name="broker_type_enum",
        ),
        nullable=False,
    )

    # ==========================================================
    # Trading Account Identity
    # ==========================================================

    login: Mapped[int] = mapped_column(
        Integer,
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
        default="USD",
        nullable=False,
    )

    leverage: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    # ==========================================================
    # Credentials
    # ==========================================================

    credentials_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # MT5 Bridge
    # ==========================================================

    bridge_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Account Type
    # ==========================================================

    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # Connection Status
    # ==========================================================

    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            name="account_status_enum",
        ),
        default=AccountStatus.DISCONNECTED,
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # Account Metrics
    # ==========================================================

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

    # ==========================================================
    # Trading Relationships
    # ==========================================================

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

    account_symbols = relationship(
        "AccountSymbol",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<TradingAccount("
            f"login={self.login}, "
            f"broker={self.broker}, "
            f"server={self.server}, "
            f"status={self.status})>"
        )
