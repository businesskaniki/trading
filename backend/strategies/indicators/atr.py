"""Average True Range indicator."""

from __future__ import annotations

from dataclasses import dataclass


def true_range(
    high: float,
    low: float,
    previous_close: float | None = None,
) -> float:
    """Calculate True Range."""
    high = float(high)
    low = float(low)

    if high < low:
        raise ValueError("High must be greater than or equal to low.")

    if previous_close is None:
        return high - low

    previous_close = float(previous_close)

    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


@dataclass
class ATR:
    """Incremental Average True Range calculator."""

    period: int
    _value: float | None = None
    _previous_close: float | None = None

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("ATR period must be greater than zero.")

    @property
    def value(self) -> float | None:
        return self._value

    def update(
        self,
        high: float,
        low: float,
        close: float,
    ) -> float:
        """Update ATR with a new candle."""
        close = float(close)

        tr = true_range(
            high,
            low,
            self._previous_close,
        )

        if self._value is None:
            self._value = tr
        else:
            multiplier = 2.0 / (self.period + 1)
            self._value = (
                (tr - self._value) * multiplier
            ) + self._value

        self._previous_close = close

        return self._value

    def reset(self) -> None:
        """Reset the indicator state."""
        self._value = None
        self._previous_close = None