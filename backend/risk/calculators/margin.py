"""Margin calculations for the AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal

from ..exceptions import RiskCalculationError
from ..models import SymbolRiskConstraints


def calculate_position_notional(
    *,
    position_size: Decimal,
    price: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate the notional value of a proposed position."""

    if position_size <= Decimal("0"):
        raise RiskCalculationError(
            "Position size must be greater than zero."
        )

    if price <= Decimal("0"):
        raise RiskCalculationError(
            "Price must be greater than zero."
        )

    return (
        position_size
        * price
        * constraints.contract_size
    )


def calculate_required_margin(
    *,
    position_size: Decimal,
    price: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """
    Calculate margin required to open a position.

    Required margin is:

        position notional × margin rate
    """

    notional = calculate_position_notional(
        position_size=position_size,
        price=price,
        constraints=constraints,
    )

    if constraints.margin_rate <= Decimal("0"):
        raise RiskCalculationError(
            "Margin rate must be greater than zero."
        )

    return notional * constraints.margin_rate


def calculate_remaining_free_margin(
    *,
    free_margin: Decimal,
    required_margin: Decimal,
) -> Decimal:
    """Calculate free margin remaining after the proposed trade."""

    if free_margin < Decimal("0"):
        raise RiskCalculationError(
            "Free margin cannot be negative."
        )

    if required_margin < Decimal("0"):
        raise RiskCalculationError(
            "Required margin cannot be negative."
        )

    return free_margin - required_margin