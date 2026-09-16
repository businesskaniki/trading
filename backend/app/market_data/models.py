from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class MarketTick:
    """
    AQE-native representation of a live market tick.

    This model deliberately contains no MT5-specific types and
    no HTTP-specific information.

    It is the object that downstream components such as the
    event bus and strategies should consume.
    """

    symbol: str
    timestamp: int

    bid: float
    ask: float

    last: float = 0.0

    volume: int = 0
    volume_real: float = 0.0

    @property
    def datetime(self) -> datetime:
        """
        Return the tick timestamp as a timezone-aware UTC datetime.
        """

        return datetime.fromtimestamp(
            self.timestamp,
            tz=timezone.utc,
        )

    @property
    def spread(self) -> float:
        """
        Return the bid/ask spread.
        """

        return self.ask - self.bid

    @property
    def mid(self) -> float:
        """
        Return the midpoint between bid and ask.
        """

        return (self.bid + self.ask) / 2.0

    def validation_errors(self) -> list[str]:
        """
        Return all validation errors found on this tick.

        This method is intentionally more informative than
        `is_valid()` so malformed broker data can be diagnosed
        without guessing which field failed validation.
        """

        errors: list[str] = []

        # -------------------------------------------------------------
        # Symbol
        # -------------------------------------------------------------

        if not isinstance(self.symbol, str):
            errors.append(f"symbol must be a string, got {type(self.symbol).__name__}")

        elif not self.symbol.strip():
            errors.append("symbol must not be empty")

        # -------------------------------------------------------------
        # Timestamp
        # -------------------------------------------------------------

        if not isinstance(self.timestamp, int):
            errors.append("timestamp must be an integer")

        elif self.timestamp <= 0:
            errors.append(f"timestamp must be greater than 0, got {self.timestamp}")

        # -------------------------------------------------------------
        # Bid
        # -------------------------------------------------------------

        if not self._is_finite_number(self.bid):
            errors.append(f"bid must be finite, got {self.bid!r}")

        elif self.bid < 0:
            errors.append(f"bid must be >= 0, got {self.bid}")

        # -------------------------------------------------------------
        # Ask
        # -------------------------------------------------------------

        if not self._is_finite_number(self.ask):
            errors.append(f"ask must be finite, got {self.ask!r}")

        elif self.ask < 0:
            errors.append(f"ask must be >= 0, got {self.ask}")

        # -------------------------------------------------------------
        # Bid / Ask relationship
        #
        # Only compare when both values are finite. This prevents
        # duplicate/noisy errors caused by NaN or infinity.
        # -------------------------------------------------------------

        if (
            self._is_finite_number(self.bid)
            and self._is_finite_number(self.ask)
            and self.ask < self.bid
        ):
            errors.append(f"ask ({self.ask}) must be >= bid ({self.bid})")

        # -------------------------------------------------------------
        # Last
        # -------------------------------------------------------------

        if not self._is_finite_number(self.last):
            errors.append(f"last must be finite, got {self.last!r}")

        elif self.last < 0:
            errors.append(f"last must be >= 0, got {self.last}")

        # -------------------------------------------------------------
        # Volume
        # -------------------------------------------------------------

        if not isinstance(self.volume, int):
            errors.append(
                f"volume must be an integer, got " f"{type(self.volume).__name__}"
            )

        elif self.volume < 0:
            errors.append(f"volume must be >= 0, got {self.volume}")

        # -------------------------------------------------------------
        # Real volume
        # -------------------------------------------------------------

        if not self._is_finite_number(self.volume_real):
            errors.append(f"volume_real must be finite, got {self.volume_real!r}")

        elif self.volume_real < 0:
            errors.append(f"volume_real must be >= 0, got {self.volume_real}")

        return errors

    def is_valid(self) -> bool:
        """
        Return True when the tick passes all basic sanity checks.
        """

        return not self.validation_errors()

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        """
        Return True when value is a finite int or float.

        Booleans are explicitly rejected because bool is a subclass
        of int in Python.
        """

        if isinstance(value, bool):
            return False

        if not isinstance(value, (int, float)):
            return False

        return math.isfinite(float(value))


@dataclass(frozen=True, slots=True)
class MarketCandle:
    """
    AQE-native OHLCV candle.
    """

    symbol: str
    timeframe: str

    timestamp: int

    open: float
    high: float
    low: float
    close: float

    volume: int = 0
    spread: int = 0

    @property
    def datetime(self) -> datetime:
        """
        Return the candle timestamp as a timezone-aware UTC datetime.
        """

        return datetime.fromtimestamp(
            self.timestamp,
            tz=timezone.utc,
        )

    def validation_errors(self) -> list[str]:
        """
        Return all validation errors found on this candle.
        """

        errors: list[str] = []

        # -------------------------------------------------------------
        # Symbol
        # -------------------------------------------------------------

        if not isinstance(self.symbol, str):
            errors.append(f"symbol must be a string, got {type(self.symbol).__name__}")

        elif not self.symbol.strip():
            errors.append("symbol must not be empty")

        # -------------------------------------------------------------
        # Timeframe
        # -------------------------------------------------------------

        if not isinstance(self.timeframe, str):
            errors.append("timeframe must be a string")

        elif not self.timeframe.strip():
            errors.append("timeframe must not be empty")

        # -------------------------------------------------------------
        # Timestamp
        # -------------------------------------------------------------

        if not isinstance(self.timestamp, int):
            errors.append("timestamp must be an integer")

        elif self.timestamp <= 0:
            errors.append(f"timestamp must be greater than 0, got {self.timestamp}")

        # -------------------------------------------------------------
        # OHLC
        # -------------------------------------------------------------

        prices = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }

        for name, value in prices.items():

            if not self._is_finite_number(value):
                errors.append(f"{name} must be finite, got {value!r}")

            elif value < 0:
                errors.append(f"{name} must be >= 0, got {value}")

        # -------------------------------------------------------------
        # OHLC relationships
        # -------------------------------------------------------------

        finite_prices = all(self._is_finite_number(value) for value in prices.values())

        if finite_prices:

            if self.high < self.low:
                errors.append(f"high ({self.high}) must be >= low ({self.low})")

            if self.high < max(
                self.open,
                self.close,
            ):
                errors.append(
                    f"high ({self.high}) must be >= "
                    f"open/close ({self.open}, {self.close})"
                )

            if self.low > min(
                self.open,
                self.close,
            ):
                errors.append(
                    f"low ({self.low}) must be <= "
                    f"open/close ({self.open}, {self.close})"
                )

        # -------------------------------------------------------------
        # Volume
        # -------------------------------------------------------------

        if not isinstance(self.volume, int):
            errors.append(
                f"volume must be an integer, got " f"{type(self.volume).__name__}"
            )

        elif self.volume < 0:
            errors.append(f"volume must be >= 0, got {self.volume}")

        # -------------------------------------------------------------
        # Spread
        # -------------------------------------------------------------

        if not isinstance(self.spread, int):
            errors.append(
                f"spread must be an integer, got " f"{type(self.spread).__name__}"
            )

        elif self.spread < 0:
            errors.append(f"spread must be >= 0, got {self.spread}")

        return errors

    def is_valid(self) -> bool:
        """
        Return True when the candle passes all basic sanity checks.
        """

        return not self.validation_errors()

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        """
        Return True when value is a finite int or float.

        Booleans are explicitly rejected.
        """

        if isinstance(value, bool):
            return False

        if not isinstance(value, (int, float)):
            return False

        return math.isfinite(float(value))
