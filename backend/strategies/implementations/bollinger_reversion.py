"""Bollinger Band mean-reversion strategy with ATR-based risk management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from strategies.core.base import BaseStrategy
from strategies.core.context import StrategyContext
from strategies.core.enums import (
    OrderType,
    SignalDirection,
    SignalType,
    Timeframe,
)
from strategies.core.registry import register_strategy
from strategies.core.signal import TradingSignal
from strategies.indicators import ATR, BollingerBands


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    bollinger: BollingerBands
    atr: ATR
    previous_close: float | None = None
    previous_upper: float | None = None
    previous_lower: float | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("bollinger_reversion")
class BollingerReversionStrategy(BaseStrategy):
    """
    Bollinger Band mean-reversion strategy.

    Long:
        Price moves from below the lower Bollinger Band
        back inside the bands.

    Short:
        Price moves from above the upper Bollinger Band
        back inside the bands.

    Stop-loss and take-profit are calculated using ATR.
    """

    DEFAULT_PARAMETERS = {
        "bollinger_period": 20,
        "bollinger_deviation": 2.0,
        "atr_period": 14,
        "stop_loss_atr": 1.5,
        "take_profit_atr": 3.0,
        "confidence": 0.70,
    }

    def __init__(
        self,
        config,
        context: StrategyContext,
    ) -> None:
        super().__init__(config, context)

        parameters = {
            **self.DEFAULT_PARAMETERS,
            **config.parameters,
        }

        self._bollinger_period = int(parameters["bollinger_period"])
        self._bollinger_deviation = float(parameters["bollinger_deviation"])
        self._atr_period = int(parameters["atr_period"])
        self._stop_loss_atr = float(parameters["stop_loss_atr"])
        self._take_profit_atr = float(parameters["take_profit_atr"])
        self._confidence = float(parameters["confidence"])

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Warm up indicators using historical candles."""
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                state = self._get_state(symbol, timeframe)

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    count=max(
                        self._bollinger_period * 3,
                        self._atr_period * 3,
                        100,
                    ),
                )

                for candle in candles:
                    self._update_indicators(
                        state,
                        candle.high,
                        candle.low,
                        candle.close,
                    )

    async def on_start(self) -> None:
        """Start the strategy."""
        return None

    async def on_stop(self) -> None:
        """Stop the strategy."""
        return None

    async def on_shutdown(self) -> None:
        """Release indicator state."""
        self._states.clear()

    async def on_candle(
        self,
        candle,
    ) -> TradingSignal | None:
        """Process a completed candle."""
        symbol = candle.symbol
        timeframe = Timeframe(candle.timeframe)

        state = self._get_state(symbol, timeframe)

        bands, atr_value = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_close = state.previous_close
        previous_upper = state.previous_upper
        previous_lower = state.previous_lower

        state.previous_close = float(candle.close)
        state.previous_upper = bands.upper
        state.previous_lower = bands.lower

        if previous_close is None or previous_upper is None or previous_lower is None:
            return None

        if atr_value <= 0:
            return None

        timestamp = self._normalize_timestamp(candle.timestamp)

        if state.last_signal_timestamp == timestamp:
            return None

        current_close = float(candle.close)

        direction: SignalDirection | None = None
        reason: str | None = None

        # Price was below the lower band and has
        # returned inside the bands.
        if previous_close <= previous_lower and current_close > bands.lower:
            direction = SignalDirection.LONG
            reason = "Price reverted above the lower " "Bollinger Band"

        # Price was above the upper band and has
        # returned inside the bands.
        elif previous_close >= previous_upper and current_close < bands.upper:
            direction = SignalDirection.SHORT
            reason = "Price reverted below the upper " "Bollinger Band"

        if direction is None:
            return None

        entry_price = Decimal(str(candle.close))
        atr = Decimal(str(atr_value))

        stop_distance = atr * Decimal(str(self._stop_loss_atr))
        target_distance = atr * Decimal(str(self._take_profit_atr))

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + target_distance
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - target_distance

        state.last_signal_timestamp = timestamp

        return TradingSignal(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            signal_type=SignalType.ENTRY,
            direction=direction,
            order_type=OrderType.MARKET,
            timestamp=timestamp,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=self._confidence,
            reason=reason,
            metadata={
                "middle_band": bands.middle,
                "upper_band": bands.upper,
                "lower_band": bands.lower,
                "standard_deviation": (bands.standard_deviation),
                "atr": atr_value,
                "bollinger_period": (self._bollinger_period),
                "bollinger_deviation": (self._bollinger_deviation),
                "stop_loss_atr": (self._stop_loss_atr),
                "take_profit_atr": (self._take_profit_atr),
            },
        )

    def _get_state(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> _IndicatorState:
        """Get or create isolated indicator state."""
        key = (symbol, timeframe)

        state = self._states.get(key)

        if state is None:
            state = _IndicatorState(
                bollinger=BollingerBands(
                    period=self._bollinger_period,
                    deviation=self._bollinger_deviation,
                ),
                atr=ATR(self._atr_period),
            )
            self._states[key] = state

        return state

    @staticmethod
    def _update_indicators(
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ):
        """Update Bollinger Bands and ATR from one candle."""
        bands = state.bollinger.update(float(close))

        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=float(close),
        )

        return bands, atr_value

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        """Normalize timestamp to timezone-aware UTC."""
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)
