"""Position-level risk rules."""

from __future__ import annotations

from .base import RiskRule, RuleResult
from ..enums import RiskRejectionReason
from ..models import RiskContext


class PositionRiskRule(RiskRule):
    """Validate open-position constraints."""

    name = "position_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """Evaluate position-related risk constraints."""

        config = context.config

        if context.open_position_count >= config.max_open_positions:
            return RuleResult.reject(
                RiskRejectionReason.MAX_OPEN_POSITIONS,
                (
                    "Maximum number of open positions has been reached: "
                    f"{config.max_open_positions}."
                ),
            )

        if context.symbol_position_count >= config.max_positions_per_symbol:
            return RuleResult.reject(
                RiskRejectionReason.MAX_SYMBOL_EXPOSURE,
                (
                    "Maximum number of positions for symbol "
                    f"{context.signal.symbol.upper()} has been reached: "
                    f"{config.max_positions_per_symbol}."
                ),
            )

        return RuleResult.pass_()