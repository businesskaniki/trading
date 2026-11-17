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
    """Calculate position notional as quantity × price × contract size."""
    if not position_size.is_finite() or position_size <= Decimal("0"):
        raise RiskCalculationError("Position size must be finite and greater than zero.")
    if not price.is_finite() or price <= Decimal("0"):
        raise RiskCalculationError("Price must be finite and greater than zero.")
    if not constraints.contract_size.is_finite() or constraints.contract_size <= Decimal("0"):
        raise RiskCalculationError("Contract size must be finite and greater than zero.")
    return position_size * price * constraints.contract_size


def calculate_required_margin(
    *,
    position_size: Decimal,
    price: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate formula-based margin; requires an explicitly configured rate."""
    margin_rate = constraints.margin_rate
    if margin_rate is None:
        raise RiskCalculationError(
            "Formula margin rate is unavailable. A broker margin assessment "
            "or an explicitly configured positive margin_rate is required."
        )
    if not margin_rate.is_finite() or margin_rate <= Decimal("0"):
        raise RiskCalculationError("Margin rate must be finite and greater than zero.")
    notional = calculate_position_notional(
        position_size=position_size,
        price=price,
        constraints=constraints,
    )
    return notional * margin_rate


def calculate_remaining_free_margin(
    *,
    free_margin: Decimal,
    required_margin: Decimal,
) -> Decimal:
    """Return free margin after the incremental margin requirement."""
    if not free_margin.is_finite() or free_margin < Decimal("0"):
        raise RiskCalculationError("Free margin must be finite and cannot be negative.")
    if not required_margin.is_finite() or required_margin < Decimal("0"):
        raise RiskCalculationError("Required margin must be finite and cannot be negative.")
    return free_margin - required_margin
