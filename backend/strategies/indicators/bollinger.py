"""Bollinger Bands indicator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True, slots=True)
class BollingerValue:
    """Bollinger Bands calculation result."""

    middle: float
    upper: float
    lower: float
    standard_deviation: float


class BollingerBands:
    """Incremental Bollinger Bands calculator."""

    def __init__(
        self,
        period: int = 20,
        deviation: float = 2.0,
    ) -> None:
        if period <= 0:
            raise ValueError(
                "Bollinger period must be greater than zero."
            )

        if deviation < 0:
            raise ValueError(
                "Bollinger deviation cannot be negative."
            )

        self.period = period
        self.deviation = float(deviation)
        self._values: deque[float] = deque(
            maxlen=period
        )
        self._value: BollingerValue | None = None

    @property
    def value(self) -> BollingerValue | None:
        return self._value

    def update(self, value: float) -> BollingerValue:
        """Update Bollinger Bands with a new price."""
        self._values.append(float(value))

        middle = sum(self._values) / len(self._values)

        variance = sum(
            (item - middle) ** 2
            for item in self._values
        ) / len(self._values)

        standard_deviation = sqrt(variance)

        upper = (
            middle
            + (self.deviation * standard_deviation)
        )

        lower = (
            middle
            - (self.deviation * standard_deviation)
        )

        self._value = BollingerValue(
            middle=middle,
            upper=upper,
            lower=lower,
            standard_deviation=standard_deviation,
        )

        return self._value

    def reset(self) -> None:
        """Reset indicator state."""
        self._values.clear()
        self._value = None