"""Position-level risk rules."""

from __future__ import annotations

from .base import RiskRule, RuleResult
from ..enums import RiskRejectionReason
from ..models import RiskContext


class PositionRiskRule(RiskRule):
    """Validate open-position constraints."""

    name = "position_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """Evaluate position-count constraints."""

        config = context.config

        # --------------------------------------------------------------
        # Portfolio position count
        # --------------------------------------------------------------

        if context.open_position_count >= config.max_open_positions:
            return RuleResult.reject(
                RiskRejectionReason.MAX_OPEN_POSITIONS,
                (
                    "Maximum number of open positions has been reached: "
                    f"{config.max_open_positions}."
                ),
            )

        # --------------------------------------------------------------
        # Per-symbol position count
        #
        # This is a position-count constraint, not a notional exposure
        # constraint. The latter is handled by ExposureRiskRule.
        # --------------------------------------------------------------

        if context.symbol_position_count >= config.max_positions_per_symbol:
            return RuleResult.reject(
                RiskRejectionReason.MAX_POSITIONS_PER_SYMBOL,
                (
                    "Maximum number of positions for symbol "
                    f"{context.signal.symbol.upper()} has been reached: "
                    f"{config.max_positions_per_symbol}."
                ),
            )

        return RuleResult.pass_()