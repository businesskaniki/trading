"""Exposure calculations for the AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal

from ..exceptions import RiskCalculationError
from ..models import PositionRiskSnapshot, SymbolRiskConstraints


def calculate_position_exposure(
    quantity: Decimal,
    price: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate the absolute notional exposure of a position.

    Exposure is calculated as:

        quantity × price × contract_size
    """

    if quantity <= Decimal("0"):
        raise RiskCalculationError("Quantity must be greater than zero.")

    if price <= Decimal("0"):
        raise RiskCalculationError("Price must be greater than zero.")

    if constraints.contract_size <= Decimal("0"):
        raise RiskCalculationError("Contract size must be greater than zero.")

    return quantity * price * constraints.contract_size


def calculate_position_risk_exposure(
    position: PositionRiskSnapshot,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate the notional exposure of an existing position."""

    return calculate_position_exposure(
        quantity=position.quantity,
        price=position.current_price,
        constraints=constraints,
    )


def calculate_total_exposure(
    positions: list[PositionRiskSnapshot],
    constraints_by_symbol: dict[str, SymbolRiskConstraints],
) -> Decimal:
    """Calculate total absolute notional exposure."""

    total = Decimal("0")

    for position in positions:
        symbol = position.symbol.upper()

        constraints = constraints_by_symbol.get(symbol)

        if constraints is None:
            raise RiskCalculationError(f"Missing symbol constraints for {symbol}.")

        total += calculate_position_risk_exposure(
            position=position,
            constraints=constraints,
        )

    return total


def calculate_symbol_exposure(
    positions: list[PositionRiskSnapshot],
    symbol: str,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate total absolute exposure for one symbol."""

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        raise RiskCalculationError("Symbol cannot be empty.")

    total = Decimal("0")

    for position in positions:
        if position.symbol.upper() != normalized_symbol:
            continue

        total += calculate_position_risk_exposure(
            position=position,
            constraints=constraints,
        )

    return total
