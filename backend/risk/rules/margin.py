"""Margin-related risk rules for the AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal

from ..calculators.margin import (
    calculate_remaining_free_margin,
    calculate_required_margin,
)
from ..enums import RiskRejectionReason
from ..exceptions import RiskCalculationError
from ..models import RiskContext
from .base import RiskRule, RuleResult


class MarginRiskRule(RiskRule):
    """
    Validate that a proposed trade can be funded by available margin.

    The rule evaluates only the incremental margin required by the
    proposed position.

    Existing positions are already reflected in
    ``context.account.free_margin``.
    """

    name = "margin_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """
        Evaluate whether the proposed trade fits within free margin.

        Required margin:

            position_size
            × entry_price
            × contract_size
            × margin_rate

        The trade is rejected when the required margin is greater than
        the account's currently available free margin.
        """

        position_size = context.proposed_position_size

        if position_size is None:
            return RuleResult.reject(
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Proposed position size is required for margin evaluation.",
            )

        if position_size <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Proposed position size must be greater than zero.",
            )

        entry_price = context.entry_price

        if entry_price <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INVALID_SIGNAL,
                "Entry price must be greater than zero for margin evaluation.",
            )

        free_margin = context.account.free_margin

        if free_margin < Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_MARGIN,
                f"Account free margin is negative ({free_margin}).",
            )

        try:
            required_margin = calculate_required_margin(
                position_size=position_size,
                price=entry_price,
                constraints=context.symbol_constraints,
            )

            remaining_free_margin = calculate_remaining_free_margin(
                free_margin=free_margin,
                required_margin=required_margin,
            )
        except (ValueError, RiskCalculationError) as exc:
            raise RiskCalculationError(
                f"Unable to calculate required margin: {exc}"
            ) from exc

        if remaining_free_margin < Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_MARGIN,
                (
                    "The proposed trade requires more margin than the "
                    "account currently has available. "
                    f"Required margin: {required_margin}, "
                    f"free margin: {free_margin}, "
                    f"remaining free margin: {remaining_free_margin}."
                ),
            )

        return RuleResult.pass_()
