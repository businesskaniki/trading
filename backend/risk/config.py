"""Risk Engine configuration."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskConfig(BaseModel):
    """Configuration controlling portfolio, trade, and exposure risk."""

    model_config = ConfigDict(extra="forbid")

    # ------------------------------------------------------------------
    # Trade risk
    # ------------------------------------------------------------------

    risk_per_trade: Decimal = Field(
        default=Decimal("0.01"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )

    max_risk_per_trade: Decimal = Field(
        default=Decimal("0.01"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )

    max_portfolio_risk: Decimal = Field(
        default=Decimal("0.05"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )

    # ------------------------------------------------------------------
    # Loss and drawdown protection
    # ------------------------------------------------------------------

    max_daily_loss: Decimal = Field(
        default=Decimal("0.03"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )

    max_drawdown: Decimal = Field(
        default=Decimal("0.10"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )

    # ------------------------------------------------------------------
    # Position limits
    # ------------------------------------------------------------------

    max_open_positions: int = Field(
        default=10,
        ge=1,
    )

    max_positions_per_symbol: int = Field(
        default=1,
        ge=1,
    )

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    min_position_size: Decimal = Field(
        default=Decimal("0.01"),
        gt=Decimal("0"),
    )

    max_position_size: Decimal = Field(
        default=Decimal("100"),
        gt=Decimal("0"),
    )

    # ------------------------------------------------------------------
    # Exposure limits
    #
    # These are NOT percentages of risk.
    # They represent maximum notional exposure as a fraction of equity.
    # ------------------------------------------------------------------

    max_portfolio_exposure: Decimal = Field(
        default=Decimal("5"),
        gt=Decimal("0"),
    )

    max_symbol_exposure: Decimal = Field(
        default=Decimal("2"),
        gt=Decimal("0"),
    )

    max_strategy_exposure: Decimal = Field(
        default=Decimal("3"),
        gt=Decimal("0"),
    )

    # ------------------------------------------------------------------
    # Trade protection
    # ------------------------------------------------------------------

    require_stop_loss: bool = True

    min_risk_reward: Decimal = Field(
        default=Decimal("1"),
        gt=Decimal("0"),
    )

    # ------------------------------------------------------------------
    # Symbol restrictions
    # ------------------------------------------------------------------

    allowed_symbols: set[str] | None = None

    @field_validator("allowed_symbols")
    @classmethod
    def normalize_symbols(
        cls,
        value: set[str] | None,
    ) -> set[str] | None:
        """Normalize configured symbols."""

        if value is None:
            return None

        normalized = {symbol.strip().upper() for symbol in value if symbol.strip()}

        return normalized or None
