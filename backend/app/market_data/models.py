from __future__ import annotations

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

    def is_valid(self) -> bool:
        """
        Basic market-data sanity check.
        """

        if not self.symbol:
            return False

        if self.timestamp <= 0:
            return False

        if self.bid < 0 or self.ask < 0:
            return False

        if self.ask < self.bid:
            return False

        if self.last < 0:
            return False

        if self.volume < 0:
            return False

        if self.volume_real < 0:
            return False

        return True


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

    def is_valid(self) -> bool:
        """
        Basic OHLCV sanity check.
        """

        if not self.symbol:
            return False

        if not self.timeframe:
            return False

        if self.timestamp <= 0:
            return False

        if (
            min(
                self.open,
                self.high,
                self.low,
                self.close,
            )
            < 0
        ):
            return False

        if self.high < self.low:
            return False

        if self.high < max(
            self.open,
            self.close,
        ):
            return False

        if self.low > min(
            self.open,
            self.close,
        ):
            return False

        if self.volume < 0:
            return False

        if self.spread < 0:
            return False

        return True
