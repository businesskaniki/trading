"""Technical indicator helpers."""

from decimal import Decimal


def sma(values: list[Decimal], period: int) -> Decimal:
    if period <= 0:
        raise ValueError("period must be greater than zero")
    if len(values) < period:
        raise ValueError("not enough values for period")
    window = values[-period:]
    return sum(window) / Decimal(period)


def true_range(high: Decimal, low: Decimal, previous_close: Decimal) -> Decimal:
    return max(high - low, abs(high - previous_close), abs(low - previous_close))
