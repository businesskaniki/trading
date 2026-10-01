"""Database model for the AQE strategy catalog."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.database.base import TimestampMixin
from app.database.base import UUIDMixin


class StrategyDefinition(UUIDMixin, TimestampMixin, Base):
    """
    Persisted catalog entry for an AQE strategy implementation.

    The Python StrategyRegistry is the source of truth for which
    strategy implementations exist.

    This table is a synchronized database representation of those
    implementations and is used by the API, configuration system,
    account assignment system, and runtime validation.

    Strategy definitions are retired rather than deleted when a
    strategy disappears from the codebase. This preserves historical
    StrategyRun records.
    """

    __tablename__ = "strategy_definitions"

    __table_args__ = (
        Index(
            "ix_strategy_definition_name",
            "name",
        ),
        Index(
            "ix_strategy_definition_available",
            "available",
        ),
        Index(
            "ix_strategy_definition_version",
            "version",
        ),
        Index(
            "ix_strategy_definition_available_name",
            "available",
            "name",
        ),
    )

    # ------------------------------------------------------------------
    # IDENTITY
    # ------------------------------------------------------------------

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # HUMAN-READABLE METADATA
    # ------------------------------------------------------------------

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        server_default="",
    )

    author: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
        server_default="",
    )

    tags: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # ------------------------------------------------------------------
    # PYTHON IMPLEMENTATION
    # ------------------------------------------------------------------

    module_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    class_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # DEFINITION SNAPSHOT
    # ------------------------------------------------------------------

    definition_payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # ------------------------------------------------------------------
    # SYNCHRONIZATION
    # ------------------------------------------------------------------

    fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # RELATIONSHIPS
    # ------------------------------------------------------------------

    strategy_runs = relationship(
        "StrategyRun",
        back_populates="strategy_definition",
    )

    # ------------------------------------------------------------------
    # REPRESENTATION
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<StrategyDefinition("
            f"name='{self.name}', "
            f"version='{self.version}', "
            f"available={self.available}, "
            f"module='{self.module_path}', "
            f"class='{self.class_name}')>"
        )
