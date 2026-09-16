"""Monetary risk calculations for the AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal

from ..exceptions import RiskCalculationError


def calculate_risk_amount(
    equity: Decimal,
    risk_fraction: Decimal,
) -> Decimal:
    """Calculate the maximum monetary risk for a trade.

    Example:
        equity = 10,000
        risk_fraction = 0.01

        result = 100
    """

    if equity < Decimal("0"):
        raise RiskCalculationError("Account equity cannot be negative.")

    if risk_fraction <= Decimal("0"):
        raise RiskCalculationError("Risk fraction must be greater than zero.")

    if risk_fraction > Decimal("1"):
        raise RiskCalculationError("Risk fraction cannot exceed 100%.")

    return equity * risk_fraction
