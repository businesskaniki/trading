"""
Market data domain models for the AQE strategy engine.

This module defines the normalized market-data contract consumed by
strategies.

The MT5 bridge is responsible for obtaining broker data and converting
it into these models. Strategies must not communicate directly with MT5.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import PriceSource, Timeframe


class Candle(BaseModel):
    """
    Represents one OHLCV candle.

    A Candle is broker-agnostic. The MT5 bridge, backtester, or another
    market-data provider can create this object.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    timestamp: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    volume: Decimal = Field(default=Decimal("0"))
    tick_volume: int = Field(default=0, ge=0)

    spread: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("high")
    @classmethod
    def validate_high(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("high price must be greater than zero")
        return value

    @field_validator("low")
    @classmethod
    def validate_low(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("low price must be greater than zero")
        return value

    @field_validator("open", "close")
    @classmethod
    def validate_prices(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price must be greater than zero")
        return value

    @field_validator("volume")
    @classmethod
    def validate_volume(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("volume cannot be negative")
        return value

    def validate_ohlc(self) -> None:
        """Validate the internal OHLC relationship."""

        highest_price = max(self.open, self.close)
        lowest_price = min(self.open, self.close)

        if self.high < highest_price:
            raise ValueError("high price cannot be lower than open or close")

        if self.low > lowest_price:
            raise ValueError("low price cannot be higher than open or close")

        if self.high < self.low:
            raise ValueError("high price cannot be lower than low price")


class MarketData(BaseModel):
    """
    Normalized market-data snapshot for one symbol/timeframe.

    This is the primary object consumed by strategies.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    symbol: str = Field(min_length=1)
    timeframe: Timeframe

    source: PriceSource

    candles: Sequence[Candle] = Field(min_length=1)

    received_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("candles")
    @classmethod
    def validate_candles(
        cls,
        value: Sequence[Candle],
    ) -> Sequence[Candle]:
        if not value:
            raise ValueError("market data must contain at least one candle")

        timestamps = [candle.timestamp for candle in value]

        if timestamps != sorted(timestamps):
            raise ValueError("candles must be ordered chronologically")

        if len(timestamps) != len(set(timestamps)):
            raise ValueError("duplicate candle timestamps are not allowed")

        return value

    @property
    def latest(self) -> Candle:
        """Return the most recent candle."""

        return self.candles[-1]

    @property
    def previous(self) -> Candle | None:
        """Return the candle immediately preceding the latest candle."""

        if len(self.candles) < 2:
            return None

        return self.candles[-2]

    @property
    def candle_count(self) -> int:
        """Return the number of available candles."""

        return len(self.candles)

    def require_candles(self, minimum: int) -> None:
        """
        Ensure enough candles are available for a strategy.

        Raises:
            ValueError: if fewer than `minimum` candles are available.
        """

        if self.candle_count < minimum:
            raise ValueError(
                f"{self.symbol} {self.timeframe.value} requires at least "
                f"{minimum} candles, got {self.candle_count}"
            )


class Tick(BaseModel):
    """
    Represents a real-time market tick.

    Tick data is primarily useful for live execution and strategies
    requiring intrabar information.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    symbol: str = Field(min_length=1)

    timestamp: datetime

    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)

    last: Decimal | None = Field(default=None, gt=0)

    volume: Decimal = Field(default=Decimal("0"), ge=0)

    source: PriceSource

    @field_validator("ask")
    @classmethod
    def validate_ask(
        cls,
        value: Decimal,
        info,
    ) -> Decimal:
        bid = info.data.get("bid")

        if bid is not None and value < bid:
            raise ValueError("ask price cannot be lower than bid price")

        return value

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def spread(self) -> Decimal:
        """Return the current bid/ask spread."""

        return self.ask - self.bid

    @property
    def mid_price(self) -> Decimal:
        """Return the midpoint between bid and ask."""

        return (self.bid + self.ask) / Decimal("2")
