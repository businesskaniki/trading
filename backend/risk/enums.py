
"""Enumerations used by the AQE Risk Engine."""

from __future__ import annotations

from enum import StrEnum


class RiskDecisionStatus(StrEnum):
    """Final outcome of a risk evaluation."""

    APPROVED = "approved"
    REJECTED = "rejected"


class RiskRejectionReason(StrEnum):
    """Reasons why a trading signal may be rejected."""

    INVALID_SIGNAL = "invalid_signal"
    INVALID_RISK_CONFIGURATION = "invalid_risk_configuration"

    STOP_LOSS_REQUIRED = "stop_loss_required"
    INVALID_STOP_LOSS = "invalid_stop_loss"
    INVALID_TAKE_PROFIT = "invalid_take_profit"

    INSUFFICIENT_EQUITY = "insufficient_equity"
    INSUFFICIENT_MARGIN = "insufficient_margin"

    MAX_RISK_PER_TRADE = "max_risk_per_trade"
    MAX_PORTFOLIO_RISK = "max_portfolio_risk"

    MAX_OPEN_POSITIONS = "max_open_positions"
    MAX_SYMBOL_EXPOSURE = "max_symbol_exposure"
    MAX_STRATEGY_EXPOSURE = "max_strategy_exposure"

    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"

    DUPLICATE_POSITION = "duplicate_position"
    SYMBOL_NOT_ALLOWED = "symbol_not_allowed"

    POSITION_SIZE_TOO_SMALL = "position_size_too_small"
    POSITION_SIZE_TOO_LARGE = "position_size_too_large"

    INVALID_POSITION_SIZE = "invalid_position_size"
    