from decimal import Decimal

from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class AccountSymbol(UUIDMixin, TimestampMixin, Base):
    """
    Account-specific representation of a tradable symbol.

    A Symbol represents the canonical financial instrument.

    AccountSymbol represents how that instrument exists on a
    particular trading account / broker / MT5 server.

    Example:

        Canonical symbol:
            EURUSD

        Account:
            JUSTMARKETS / MT5 / JustMarkets-Demo3

        Broker symbol:
            EURUSD.s

    The `enabled` field represents whether AQE is allowed to trade
    this symbol on this specific account.
    """

    __tablename__ = "account_symbols"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "symbol_id",
            name="uq_account_symbol",
        ),
        UniqueConstraint(
            "account_id",
            "broker_symbol",
            name="uq_account_broker_symbol",
        ),
        Index(
            "ix_account_symbols_account_id",
            "account_id",
        ),
        Index(
            "ix_account_symbols_symbol_id",
            "symbol_id",
        ),
        Index(
            "ix_account_symbols_enabled",
            "enabled",
        ),
        Index(
            "ix_account_symbols_broker_symbol",
            "broker_symbol",
        ),
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trading_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "symbols.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    account = relationship(
        "TradingAccount",
        back_populates="account_symbols",
    )

    symbol = relationship(
        "Symbol",
        back_populates="account_symbols",
    )

    # ==========================================================
    # Broker / MT5 Symbol Identity
    # ==========================================================

    broker_symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Currency Information
    # ==========================================================

    currency_base: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    currency_profit: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    currency_margin: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    # ==========================================================
    # Price Specification
    # ==========================================================

    digits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    point: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(20, 10),
        nullable=False,
    )

    # ==========================================================
    # Contract Specification
    # ==========================================================

    contract_size: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    min_volume: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    max_volume: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    volume_step: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    # ==========================================================
    # MT5 Market Watch State
    # ==========================================================

    visible: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ==========================================================
    # AQE Trading State
    # ==========================================================

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<AccountSymbol("
            f"account_id={self.account_id}, "
            f"symbol_id={self.symbol_id}, "
            f"broker_symbol='{self.broker_symbol}', "
            f"enabled={self.enabled})>"
        )
