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
    """Validate that the proposed trade fits within available free margin."""

    name = "margin_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        position_size = context.proposed_position_size
        if position_size is None or position_size <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "A positive proposed position size is required for margin evaluation.",
            )

        entry_price = context.entry_price
        if not entry_price.is_finite() or entry_price <= Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INVALID_SIGNAL,
                "Entry price must be finite and greater than zero for margin evaluation.",
            )

        free_margin = context.account.free_margin
        if not free_margin.is_finite() or free_margin < Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_MARGIN,
                f"Account free margin is invalid or negative ({free_margin}).",
            )

        assessment = context.broker_margin_assessment
        try:
            if assessment is not None:
                expected_broker_symbol = context.broker_symbol
                if not expected_broker_symbol:
                    raise RiskCalculationError(
                        "Broker margin assessment supplied without a broker symbol."
                    )
                if assessment.broker_symbol.casefold() != expected_broker_symbol.casefold():
                    raise RiskCalculationError(
                        "Broker margin assessment symbol does not match the prepared trade: "
                        f"assessment={assessment.broker_symbol!r}, "
                        f"expected={expected_broker_symbol!r}."
                    )
                if assessment.direction is not context.signal.direction:
                    raise RiskCalculationError(
                        "Broker margin assessment direction does not match the signal."
                    )
                if assessment.volume != position_size:
                    raise RiskCalculationError(
                        "Broker margin assessment volume does not match final position size: "
                        f"assessment={assessment.volume}, expected={position_size}."
                    )
                if assessment.entry_price != entry_price:
                    raise RiskCalculationError(
                        "Broker margin assessment price does not match resolved entry price: "
                        f"assessment={assessment.entry_price}, expected={entry_price}."
                    )
                required_margin = assessment.required_margin
            else:
                required_margin = calculate_required_margin(
                    position_size=position_size,
                    price=entry_price,
                    constraints=context.symbol_constraints,
                )

            remaining_free_margin = calculate_remaining_free_margin(
                free_margin=free_margin,
                required_margin=required_margin,
            )
        except (ValueError, ArithmeticError, RiskCalculationError) as exc:
            raise RiskCalculationError(f"Unable to validate required margin: {exc}") from exc

        if remaining_free_margin < Decimal("0"):
            return RuleResult.reject(
                RiskRejectionReason.INSUFFICIENT_MARGIN,
                (
                    "The proposed trade requires more margin than the account "
                    "currently has available. "
                    f"Required margin: {required_margin}, "
                    f"free margin: {free_margin}, "
                    f"remaining free margin: {remaining_free_margin}."
                ),
            )

        return RuleResult.pass_()
