"""Relative Strength Index indicator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RSI:
    """Incremental Relative Strength Index calculator."""

    period: int
    _value: float | None = None
    _previous_close: float | None = None
    _average_gain: float | None = None
    _average_loss: float | None = None

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("RSI period must be greater than zero.")

    @property
    def value(self) -> float | None:
        return self._value

    def update(self, close: float) -> float:
        """Update RSI with a new closing price."""
        close = float(close)

        if self._previous_close is None:
            self._previous_close = close
            return 50.0

        change = close - self._previous_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._average_gain is None:
            self._average_gain = gain
            self._average_loss = loss
        else:
            self._average_gain = (
                (
                    self._average_gain * (self.period - 1)
                ) + gain
            ) / self.period

            self._average_loss = (
                (
                    self._average_loss * (self.period - 1)
                ) + loss
            ) / self.period

        self._previous_close = close

        if self._average_loss == 0:
            self._value = 100.0
            return self._value

        if self._average_gain == 0:
            self._value = 0.0
            return self._value

        relative_strength = (
            self._average_gain / self._average_loss
        )

        self._value = (
            100.0
            - (100.0 / (1.0 + relative_strength))
        )

        return self._value

    def reset(self) -> None:
        """Reset the indicator state."""
        self._value = None
        self._previous_close = None
        self._average_gain = None
        self._average_loss = None