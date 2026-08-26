"""Risk-based position sizing."""

from decimal import Decimal, ROUND_DOWN


def position_size(equity: Decimal, risk_percent: Decimal, entry: Decimal, stop: Decimal, tick_size: Decimal, tick_value: Decimal, volume_step: Decimal) -> Decimal:
    if min(equity, risk_percent, entry, stop, tick_size, tick_value, volume_step) <= 0:
        raise ValueError("all sizing inputs must be positive")
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        raise ValueError("entry and stop cannot be equal")
    risk_amount = equity * risk_percent / Decimal("100")
    risk_per_unit = stop_distance / tick_size * tick_value
    raw_volume = risk_amount / risk_per_unit
    return (raw_volume / volume_step).to_integral_value(rounding=ROUND_DOWN) * volume_step
