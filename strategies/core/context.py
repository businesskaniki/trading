"""
Runtime context for the AQE strategy engine.

StrategyContext contains the information available to a strategy when
it evaluates the market.

The context is intentionally broker-agnostic. The MT5 bridge is
responsible for supplying normalized market data to the strategy engine.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    PriceSource,
    StrategyCategory,
    StrategyExecutionMode,
    Timeframe,
)
from .market_data import MarketData, Tick


class SymbolInfo(BaseModel):
    """
    Normalized trading-symbol information.

    The MT5 bridge can populate this model from the broker's symbol
    specification.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    symbol: str = Field(min_length=1)

    digits: int = Field(ge=0, le=10)

    point: Decimal = Field(gt=0)

    tick_size: Decimal = Field(gt=0)

    tick_value: Decimal = Field(gt=0)

    contract_size: Decimal = Field(gt=0)

    volume_min: Decimal = Field(gt=0)

    volume_max: Decimal = Field(gt=0)

    volume_step: Decimal = Field(gt=0)

    spread: Decimal = Field(default=Decimal("0"), ge=0)

    @property
    def price_precision(self) -> int:
        """Return the number of decimal places used by the symbol."""

        return self.digits


class StrategyConfig(BaseModel):
    """
    Runtime configuration for a strategy.

    Individual strategies can extend this model with their own
    parameters later.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="allow",
    )

    strategy_id: str = Field(min_length=1)

    name: str = Field(min_length=1)

    category: StrategyCategory

    timeframe: Timeframe

    parameters: Mapping[str, object] = Field(
        default_factory=dict,
    )

    enabled: bool = True


class AccountSnapshot(BaseModel):
    """
    Minimal account information available to strategies.

    This is deliberately a snapshot rather than a direct MT5 account
    object.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    currency: str = Field(min_length=1)

    balance: Decimal = Field(ge=0)

    equity: Decimal = Field(ge=0)

    free_margin: Decimal = Field(ge=0)

    margin_used: Decimal = Field(ge=0)

    open_positions: int = Field(default=0, ge=0)


class StrategyContext(BaseModel):
    """
    Complete runtime context supplied to a strategy.

    A strategy receives this object and uses it to make a decision.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    timestamp: datetime

    execution_mode: StrategyExecutionMode

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    strategy: StrategyConfig

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    market_data: MarketData

    tick: Tick | None = None

    symbol_info: SymbolInfo | None = None

    # ------------------------------------------------------------------
    # Multi-timeframe market data
    # ------------------------------------------------------------------

    additional_market_data: Mapping[
        Timeframe,
        MarketData,
    ] = Field(
        default_factory=dict,
    )

    # ------------------------------------------------------------------
    # Account snapshot
    # ------------------------------------------------------------------

    account: AccountSnapshot | None = None

    # ------------------------------------------------------------------
    # Runtime metadata
    # ------------------------------------------------------------------

    metadata: Mapping[str, object] = Field(
        default_factory=dict,
    )

    @property
    def symbol(self) -> str:
        """Return the symbol currently being evaluated."""

        return self.market_data.symbol

    @property
    def timeframe(self) -> Timeframe:
        """Return the primary strategy timeframe."""

        return self.market_data.timeframe

    @property
    def source(self) -> PriceSource:
        """Return the market-data source."""

        return self.market_data.source

    @property
    def latest_candle(self):
        """Return the latest candle."""

        return self.market_data.latest

    @property
    def previous_candle(self):
        """Return the previous candle, if available."""

        return self.market_data.previous

    @property
    def current_price(self) -> Decimal:
        """
        Return the best available current price.

        For live trading, the tick midpoint is preferred.

        If a tick is unavailable, the latest candle close is used.
        """

        if self.tick is not None:
            return self.tick.mid_price

        return self.market_data.latest.close

    def get_market_data(
        self,
        timeframe: Timeframe,
    ) -> MarketData | None:
        """
        Return market data for a requested timeframe.

        The primary strategy timeframe is checked first.
        """

        if timeframe == self.market_data.timeframe:
            return self.market_data

        return self.additional_market_data.get(timeframe)

    def require_market_data(
        self,
        timeframe: Timeframe,
    ) -> MarketData:
        """
        Return market data for a timeframe or raise an error.
        """

        data = self.get_market_data(timeframe)

        if data is None:
            raise ValueError(
                f"Market data for {self.symbol} {timeframe.value} " "is not available"
            )

        return data

    def require_candles(self, minimum: int) -> None:
        """
        Ensure the primary timeframe contains enough candles.
        """

        self.market_data.require_candles(minimum)
