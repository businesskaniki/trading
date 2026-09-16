"""Moving Average Convergence Divergence indicator."""

from __future__ import annotations

from dataclasses import dataclass

from .ema import EMA


@dataclass(frozen=True, slots=True)
class MACDValue:
    """MACD calculation result."""

    macd: float
    signal: float
    histogram: float


class MACD:
    """Incremental MACD calculator."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        if fast_period <= 0:
            raise ValueError(
                "MACD fast period must be greater than zero."
            )

        if slow_period <= 0:
            raise ValueError(
                "MACD slow period must be greater than zero."
            )

        if signal_period <= 0:
            raise ValueError(
                "MACD signal period must be greater than zero."
            )

        if fast_period >= slow_period:
            raise ValueError(
                "MACD fast period must be less than slow period."
            )

        self.fast = EMA(fast_period)
        self.slow = EMA(slow_period)
        self.signal = EMA(signal_period)

        self._value: MACDValue | None = None

    @property
    def value(self) -> MACDValue | None:
        return self._value

    def update(self, value: float) -> MACDValue:
        """Update MACD with a new price."""
        fast = self.fast.update(value)
        slow = self.slow.update(value)

        macd = fast - slow
        signal = self.signal.update(macd)
        histogram = macd - signal

        self._value = MACDValue(
            macd=macd,
            signal=signal,
            histogram=histogram,
        )

        return self._value

    def reset(self) -> None:
        """Reset all MACD state."""
        self.fast.reset()
        self.slow.reset()
        self.signal.reset()
        self._value = None