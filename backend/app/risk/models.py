from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class RiskProfile(
    UUIDMixin,
    TimestampMixin,
    Base,
):
    """
    Persistent risk configuration for a trading account.

    RiskProfile represents what AQE is ALLOWED to risk.

    RiskSnapshot represents what AQE's risk state WAS at a
    particular point in time. They are intentionally separate.
    """

    __tablename__ = "risk_profiles"

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "trading_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    account = relationship(
        "TradingAccount",
        back_populates="risk_profile",
    )

    # ==========================================================
    # GENERAL
    # ==========================================================

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # BASE RISK
    # ==========================================================

    base_risk_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0000"),
        nullable=False,
    )

    min_risk_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("0.2500"),
        nullable=False,
    )

    max_risk_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("2.0000"),
        nullable=False,
    )

    # ==========================================================
    # DYNAMIC RISK MULTIPLIER
    # ==========================================================

    risk_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0000"),
        nullable=False,
    )

    # ==========================================================
    # ACCOUNT LEVEL LIMITS
    # ==========================================================

    max_daily_loss_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("3.0000"),
        nullable=False,
    )

    max_drawdown_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("10.0000"),
        nullable=False,
    )

    max_open_risk_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("5.0000"),
        nullable=False,
    )

    # ==========================================================
    # POSITION LIMITS
    # ==========================================================

    max_positions: Mapped[int] = mapped_column(
        default=10,
        nullable=False,
    )

    # ==========================================================
    # EXPOSURE LIMITS
    # ==========================================================

    max_symbol_exposure_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("5.0000"),
        nullable=False,
    )

    max_strategy_exposure_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("5.0000"),
        nullable=False,
    )

    # ==========================================================
    # SAFETY
    # ==========================================================

    hard_limits_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # REPRESENTATION
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<RiskProfile("
            f"account_id={self.account_id}, "
            f"base_risk={self.base_risk_percent}, "
            f"multiplier={self.risk_multiplier})>"
        )