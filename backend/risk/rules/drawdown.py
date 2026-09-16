"""Drawdown and loss-related risk rules."""

from __future__ import annotations

from decimal import Decimal

from .base import RiskRule, RuleResult
from ..enums import RiskRejectionReason
from ..models import RiskContext


class DrawdownRiskRule(RiskRule):
    """Validate daily loss and account drawdown limits."""

    name = "drawdown_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """Evaluate daily loss and drawdown constraints."""

        account = context.account
        config = context.config

        if account.equity <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_EQUITY,
                "Account equity must be greater than zero.",
            )

        daily_loss_ratio = Decimal("0")

        if account.daily_pnl < Decimal("0"):
            daily_loss_ratio = (
                abs(account.daily_pnl) / account.equity
            )

        if daily_loss_ratio >= config.max_daily_loss:
            return RuleResult.reject(
                RiskRejectionReason.MAX_DAILY_LOSS,
                (
                    "Maximum daily loss limit has been reached. "
                    f"Limit: {config.max_daily_loss}."
                ),
            )

        drawdown_ratio = account.drawdown_ratio

        if drawdown_ratio >= config.max_drawdown:
            return RuleResult.reject(
                RiskRejectionReason.MAX_DRAWDOWN,
                (
                    "Maximum account drawdown limit has been reached. "
                    f"Limit: {config.max_drawdown}."
                ),
            )

        return RuleResult.pass_()