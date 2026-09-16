"""Position-size calculations for the AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ..exceptions import RiskCalculationError
from ..models import SymbolRiskConstraints


def calculate_stop_distance(
    entry_price: Decimal,
    stop_loss: Decimal,
) -> Decimal:
    """Return the absolute price distance between entry and stop."""

    if entry_price <= Decimal("0"):
        raise RiskCalculationError("Entry price must be greater than zero.")

    if stop_loss <= Decimal("0"):
        raise RiskCalculationError("Stop-loss price must be greater than zero.")

    distance = abs(entry_price - stop_loss)

    if distance <= Decimal("0"):
        raise RiskCalculationError("Entry price and stop-loss price cannot be equal.")

    return distance


def calculate_risk_per_unit(
    entry_price: Decimal,
    stop_loss: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate monetary risk for one unit of position size."""

    stop_distance = calculate_stop_distance(
        entry_price,
        stop_loss,
    )

    if constraints.tick_size <= Decimal("0"):
        raise RiskCalculationError("Tick size must be greater than zero.")

    if constraints.tick_value <= Decimal("0"):
        raise RiskCalculationError("Tick value must be greater than zero.")

    tick_distance = stop_distance / constraints.tick_size

    return tick_distance * constraints.tick_value


def calculate_raw_position_size(
    risk_amount: Decimal,
    entry_price: Decimal,
    stop_loss: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate position size before broker volume normalization."""

    if risk_amount <= Decimal("0"):
        raise RiskCalculationError("Risk amount must be greater than zero.")

    risk_per_unit = calculate_risk_per_unit(
        entry_price,
        stop_loss,
        constraints,
    )

    if risk_per_unit <= Decimal("0"):
        raise RiskCalculationError("Risk per unit must be greater than zero.")

    return risk_amount / risk_per_unit


def normalize_position_size(
    position_size: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Normalize position size to broker min/max/step constraints.

    The size is rounded down to the nearest valid volume step so that
    the resulting trade does not exceed the requested monetary risk.
    """

    if position_size <= Decimal("0"):
        raise RiskCalculationError("Position size must be greater than zero.")

    minimum = constraints.volume_min
    maximum = constraints.volume_max
    step = constraints.volume_step

    if minimum <= Decimal("0"):
        raise RiskCalculationError("Minimum volume must be greater than zero.")

    if maximum < minimum:
        raise RiskCalculationError("Maximum volume cannot be less than minimum volume.")

    if step <= Decimal("0"):
        raise RiskCalculationError("Volume step must be greater than zero.")

    if position_size < minimum:
        return Decimal("0")

    if position_size > maximum:
        position_size = maximum

    steps = ((position_size - minimum) / step).to_integral_value(rounding=ROUND_DOWN)

    normalized = minimum + (steps * step)

    if normalized > maximum:
        normalized = maximum

    return normalized


def calculate_position_size(
    risk_amount: Decimal,
    entry_price: Decimal,
    stop_loss: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate a broker-valid position size.

    Returns zero when the calculated size is below the broker's
    minimum volume.
    """

    raw_size = calculate_raw_position_size(
        risk_amount=risk_amount,
        entry_price=entry_price,
        stop_loss=stop_loss,
        constraints=constraints,
    )

    return normalize_position_size(
        raw_size,
        constraints,
    )


def calculate_position_risk(
    position_size: Decimal,
    entry_price: Decimal,
    stop_loss: Decimal,
    constraints: SymbolRiskConstraints,
) -> Decimal:
    """Calculate the actual monetary risk of a position."""

    if position_size <= Decimal("0"):
        raise RiskCalculationError("Position size must be greater than zero.")

    risk_per_unit = calculate_risk_per_unit(
        entry_price=entry_price,
        stop_loss=stop_loss,
        constraints=constraints,
    )

    return position_size * risk_per_unit
