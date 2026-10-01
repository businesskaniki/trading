"""Pydantic schemas for AQE strategy runs and configurations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import StrategyRunStatus, StrategyRunType

# ==========================================================
# RESPONSE / SHARED SCHEMA
# ==========================================================


class StrategyRunBase(BaseModel):
    """
    Shared StrategyRun fields exposed by the API.

    A StrategyRun represents an account-specific assignment and
    configuration of an installed StrategyDefinition.

    ``strategy_definition_id`` is the authoritative strategy identity.

    ``strategy_name`` and ``strategy_version`` are persisted snapshots
    of the selected StrategyDefinition and are not client-controlled.

    ``symbols`` is retained as a historical configuration snapshot.
    The live and backtest runtimes resolve the effective trading
    universe from AccountSymbol.
    """

    # ======================================================
    # Ownership
    # ======================================================

    account_id: UUID

    # ======================================================
    # Strategy Identity
    # ======================================================

    strategy_definition_id: UUID

    # ======================================================
    # Strategy Snapshot
    # ======================================================

    strategy_name: str

    strategy_version: str

    # ======================================================
    # Run Identity
    # ======================================================

    run_name: str

    description: str | None = None

    # ======================================================
    # Configuration State
    # ======================================================

    enabled: bool = True

    # ======================================================
    # Execution
    # ======================================================

    run_type: StrategyRunType

    status: StrategyRunStatus = StrategyRunStatus.CREATED

    # ======================================================
    # Configuration
    # ======================================================

    parameters: dict[str, Any] = Field(
        default_factory=dict,
    )

    # ------------------------------------------------------
    # Historical symbol snapshot
    # ------------------------------------------------------

    symbols: list[str] = Field(
        default_factory=list,
    )

    timeframe: str

    # ======================================================
    # Statistics
    # ======================================================

    total_trades: int = 0

    winning_trades: int = 0

    losing_trades: int = 0

    net_profit: Decimal = Decimal("0")

    max_drawdown: Decimal = Decimal("0")

    profit_factor: Decimal | None = None

    sharpe_ratio: Decimal | None = None

    expectancy: Decimal | None = None

    # ======================================================
    # Timing
    # ======================================================

    started_at: datetime | None = None

    ended_at: datetime | None = None

    # ======================================================
    # Notes
    # ======================================================

    notes: str | None = None


# ==========================================================
# CREATE SCHEMA
# ==========================================================


class StrategyRunCreate(BaseModel):
    """
    Client payload used to create a StrategyRun.

    The client selects:

        - account_id
        - strategy_definition_id
        - run configuration

    The service resolves the selected StrategyDefinition and
    derives:

        - strategy_name
        - strategy_version

    Those values are persisted on the StrategyRun as immutable
    historical snapshots.

    The effective live/backtest symbol universe is resolved from
    AccountSymbol. ``symbols`` is therefore only an optional
    historical snapshot supplied by the client.
    """

    # ======================================================
    # Ownership
    # ======================================================

    account_id: UUID

    # ======================================================
    # Strategy Identity
    # ======================================================

    strategy_definition_id: UUID

    # ======================================================
    # Run Identity
    # ======================================================

    run_name: str = Field(
        min_length=1,
        max_length=255,
    )

    description: str | None = None

    # ======================================================
    # Configuration State
    # ======================================================

    enabled: bool = True

    # ======================================================
    # Execution
    # ======================================================

    run_type: StrategyRunType

    # ======================================================
    # Configuration
    # ======================================================

    parameters: dict[str, Any] = Field(
        default_factory=dict,
    )

    # ------------------------------------------------------
    # Historical symbol snapshot
    # ------------------------------------------------------

    symbols: list[str] = Field(
        default_factory=list,
    )

    timeframe: str = Field(
        min_length=1,
        max_length=32,
    )

    # ======================================================
    # Notes
    # ======================================================

    notes: str | None = None


# ==========================================================
# UPDATE SCHEMA
# ==========================================================


class StrategyRunUpdate(BaseModel):
    """
    Payload used to update mutable StrategyRun configuration.

    The following fields are intentionally immutable:

        - account_id
        - strategy_definition_id
        - strategy_name
        - strategy_version

    Changing the account or strategy implementation creates a new
    StrategyRun rather than mutating the identity of an existing run.

    Runtime statistics and lifecycle timestamps are included because
    the existing service/repository contract supports persistence of
    those values. The execution engine should remain the authority
    that changes runtime-owned fields.
    """

    # ======================================================
    # Run Configuration
    # ======================================================

    run_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = None

    # ======================================================
    # Configuration State
    # ======================================================

    enabled: bool | None = None

    # ======================================================
    # Execution
    # ======================================================

    run_type: StrategyRunType | None = None

    status: StrategyRunStatus | None = None

    # ======================================================
    # Configuration
    # ======================================================

    parameters: dict[str, Any] | None = None

    # ------------------------------------------------------
    # Historical symbol snapshot
    # ------------------------------------------------------

    symbols: list[str] | None = None

    timeframe: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
    )

    # ======================================================
    # Statistics
    # ======================================================

    total_trades: int | None = None

    winning_trades: int | None = None

    losing_trades: int | None = None

    net_profit: Decimal | None = None

    max_drawdown: Decimal | None = None

    profit_factor: Decimal | None = None

    sharpe_ratio: Decimal | None = None

    expectancy: Decimal | None = None

    # ======================================================
    # Timing
    # ======================================================

    started_at: datetime | None = None

    ended_at: datetime | None = None

    # ======================================================
    # Notes
    # ======================================================

    notes: str | None = None


# ==========================================================
# RESPONSE SCHEMA
# ==========================================================


class StrategyRunResponse(StrategyRunBase):
    """
    StrategyRun returned to API clients.

    The response exposes both:

        strategy_definition_id
            authoritative installed-strategy identity

        strategy_name / strategy_version
            immutable historical snapshots of that definition
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    created_at: datetime

    updated_at: datetime
