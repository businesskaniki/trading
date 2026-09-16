"""Exponential Moving Average indicator."""

from __future__ import annotations

from collections.abc import Iterable


def calculate_ema(values: Iterable[float], period: int) -> list[float]:
    """Calculate EMA values for a sequence."""
    values = [float(value) for value in values]

    if period <= 0:
        raise ValueError("EMA period must be greater than zero.")

    if not values:
        return []

    multiplier = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]

    for value in values[1:]:
        ema = ((value - ema) * multiplier) + ema
        result.append(ema)

    return result


class EMA:
    """Incremental Exponential Moving Average calculator."""

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("EMA period must be greater than zero.")

        self.period = period
        self._value: float | None = None

    @property
    def value(self) -> float | None:
        return self._value

    def update(self, value: float) -> float:
        """Update the EMA with a new value."""
        value = float(value)

        if self._value is None:
            self._value = value
            return self._value

        multiplier = 2.0 / (self.period + 1)
        self._value = ((value - self._value) * multiplier) + self._value

        return self._value

    def reset(self) -> None:
        """Reset the indicator state."""
        self._value = None