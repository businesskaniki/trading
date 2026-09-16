"""Exposure-related risk rules."""

from __future__ import annotations

from decimal import Decimal

from ..calculators.exposure import (
    calculate_position_exposure,
    calculate_symbol_exposure,
    calculate_total_exposure,
)
from ..enums import RiskRejectionReason
from ..models import RiskContext
from .base import RiskRule, RuleResult


class ExposureRiskRule(RiskRule):
    """Validate portfolio, symbol, and strategy exposure."""

    name = "exposure_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """
        Evaluate exposure including the proposed trade.

        Existing positions and the proposed position are evaluated
        together so a new trade cannot push exposure beyond a limit.
        """

        if context.proposed_position_size is None:
            return RuleResult.reject(
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Proposed position size is required for exposure evaluation.",
            )

        account = context.account
        config = context.config
        signal = context.signal
        constraints = context.symbol_constraints

        proposed_exposure = (
            context.proposed_position_size
            * context.entry_price
            * constraints.contract_size
        )

        current_portfolio_exposure = calculate_total_exposure(
            context.positions,
        )

        current_symbol_exposure = calculate_symbol_exposure(
            context.positions,
            signal.symbol,
        )

        current_strategy_exposure = sum(
            (
                calculate_position_exposure(position)
                for position in context.positions
                if position.strategy_id == signal.strategy_id
            ),
            Decimal("0"),
        )

        proposed_portfolio_exposure = current_portfolio_exposure + proposed_exposure

        proposed_symbol_exposure = current_symbol_exposure + proposed_exposure

        proposed_strategy_exposure = current_strategy_exposure + proposed_exposure

        # Exposure limits are not risk percentages.
        # They represent multiples of account equity.
        max_portfolio_exposure = account.equity * config.max_portfolio_exposure

        max_symbol_exposure = account.equity * config.max_symbol_exposure

        max_strategy_exposure = account.equity * config.max_strategy_exposure

        if proposed_portfolio_exposure > max_portfolio_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_PORTFOLIO_RISK,
                (
                    "The proposed trade would exceed the maximum "
                    "portfolio exposure. "
                    f"Current: {current_portfolio_exposure}, "
                    f"proposed: {proposed_portfolio_exposure}, "
                    f"maximum: {max_portfolio_exposure}."
                ),
            )

        if proposed_symbol_exposure > max_symbol_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_SYMBOL_EXPOSURE,
                (
                    f"The proposed {signal.symbol.upper()} trade would "
                    "exceed the maximum symbol exposure. "
                    f"Current: {current_symbol_exposure}, "
                    f"proposed: {proposed_symbol_exposure}, "
                    f"maximum: {max_symbol_exposure}."
                ),
            )

        if proposed_strategy_exposure > max_strategy_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_STRATEGY_EXPOSURE,
                (
                    f"The proposed trade for strategy "
                    f"{signal.strategy_id} would exceed the maximum "
                    "strategy exposure. "
                    f"Current: {current_strategy_exposure}, "
                    f"proposed: {proposed_strategy_exposure}, "
                    f"maximum: {max_strategy_exposure}."
                ),
            )

        return RuleResult.pass_()
