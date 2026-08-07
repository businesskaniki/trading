from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class EmailVerification(UUIDMixin, TimestampMixin, Base):
    """
    Stores OTPs used to verify a user's email address.

    A new record is created every time an OTP is sent.
    Old records can be deleted or marked as verified.
    """

    __tablename__ = "email_verifications"

    __table_args__ = (
        Index("ix_email_verification_user", "user_id"),
        Index("ix_email_verification_expires", "expires_at"),
        Index("ix_email_verification_verified", "verified"),
    )

    # ==========================================================
    # Relationship
    # ==========================================================

    user_id: Mapped[UUID] = mapped_column(
    ForeignKey(
        "users.id",
        ondelete="CASCADE",
    ),
    unique=True,
    nullable=False,
)

    user = relationship(
        "User",
        back_populates="email_verifications",
    )

    # ==========================================================
    # OTP
    # ==========================================================

    otp_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ==========================================================
    # Security
    # ==========================================================

    verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<EmailVerification("
            f"user_id={self.user_id}, "
            f"verified={self.verified}, "
            f"expires_at={self.expires_at})>"
        )