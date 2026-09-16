"""Account-level risk rules."""

from __future__ import annotations

from decimal import Decimal

from .base import RiskRule, RuleResult
from ..enums import RiskRejectionReason
from ..models import RiskContext


class AccountRiskRule(RiskRule):
    """Validate account-level conditions before approving a trade."""

    name = "account_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """Evaluate account-level risk constraints."""

        account = context.account

        if account.equity <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_EQUITY,
                "Account equity must be greater than zero.",
            )

        if account.free_margin < Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_MARGIN,
                "Account free margin cannot be negative.",
            )

        return RuleResult.pass_()