"""Enumerations used by the AQE Risk Engine."""

from __future__ import annotations

from enum import StrEnum


class RiskDecisionStatus(StrEnum):
    """Final outcome of a risk evaluation."""

    APPROVED = "approved"
    REJECTED = "rejected"


class RiskRejectionReason(StrEnum):
    """Reasons why a trading signal may be rejected."""

    # ------------------------------------------------------------------
    # Signal and configuration validation
    # ------------------------------------------------------------------

    INVALID_SIGNAL = "invalid_signal"
    INVALID_RISK_CONFIGURATION = "invalid_risk_configuration"

    # ------------------------------------------------------------------
    # Trade protection
    # ------------------------------------------------------------------

    STOP_LOSS_REQUIRED = "stop_loss_required"
    INVALID_STOP_LOSS = "invalid_stop_loss"
    INVALID_TAKE_PROFIT = "invalid_take_profit"

    # ------------------------------------------------------------------
    # Account-level constraints
    # ------------------------------------------------------------------

    INSUFFICIENT_EQUITY = "insufficient_equity"
    INSUFFICIENT_MARGIN = "insufficient_margin"

    # ------------------------------------------------------------------
    # Monetary risk limits
    #
    # These represent actual monetary risk, normally measured against
    # the account's equity and the trade's stop-loss distance.
    # ------------------------------------------------------------------

    MAX_RISK_PER_TRADE = "max_risk_per_trade"
    MAX_PORTFOLIO_RISK = "max_portfolio_risk"

    # ------------------------------------------------------------------
    # Position-count constraints
    # ------------------------------------------------------------------

    MAX_OPEN_POSITIONS = "max_open_positions"
    MAX_POSITIONS_PER_SYMBOL = "max_positions_per_symbol"

    # ------------------------------------------------------------------
    # Notional exposure constraints
    #
    # These represent absolute notional exposure:
    #
    #     quantity × price × contract_size
    #
    # They are distinct from monetary risk.
    # ------------------------------------------------------------------

    MAX_PORTFOLIO_EXPOSURE = "max_portfolio_exposure"
    MAX_SYMBOL_EXPOSURE = "max_symbol_exposure"
    MAX_STRATEGY_EXPOSURE = "max_strategy_exposure"

    # ------------------------------------------------------------------
    # Loss and drawdown protection
    # ------------------------------------------------------------------

    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"

    # ------------------------------------------------------------------
    # Position and symbol validation
    # ------------------------------------------------------------------

    DUPLICATE_POSITION = "duplicate_position"
    SYMBOL_NOT_ALLOWED = "symbol_not_allowed"

    # ------------------------------------------------------------------
    # Position-size validation
    # ------------------------------------------------------------------

    POSITION_SIZE_TOO_SMALL = "position_size_too_small"
    POSITION_SIZE_TOO_LARGE = "position_size_too_large"
    INVALID_POSITION_SIZE = "invalid_position_size"
