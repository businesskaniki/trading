"""Donchian Channel breakout strategy with ATR-based risk management."""

from __future__ import annotations

from collections import deque
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
from strategies.indicators import ATR


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    highs: deque[float]
    lows: deque[float]
    atr: ATR
    previous_close: float | None = None
    previous_upper: float | None = None
    previous_lower: float | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("donchian_breakout")
class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel breakout strategy.

    Long:
        Price breaks above the previous Donchian upper channel.

    Short:
        Price breaks below the previous Donchian lower channel.

    The current candle is excluded from the breakout channel so that
    the strategy detects an actual breakout rather than comparing the
    candle against a channel containing itself.

    Stop-loss and take-profit are calculated using ATR.
    """

    DEFAULT_PARAMETERS = {
        "donchian_period": 20,
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

        self._donchian_period = int(parameters["donchian_period"])
        self._atr_period = int(parameters["atr_period"])
        self._stop_loss_atr = float(parameters["stop_loss_atr"])
        self._take_profit_atr = float(parameters["take_profit_atr"])
        self._confidence = float(parameters["confidence"])

        if self._donchian_period <= 0:
            raise ValueError("donchian_period must be greater than zero.")

        if self._atr_period <= 0:
            raise ValueError("atr_period must be greater than zero.")

        if self._stop_loss_atr <= 0:
            raise ValueError("stop_loss_atr must be greater than zero.")

        if self._take_profit_atr <= 0:
            raise ValueError("take_profit_atr must be greater than zero.")

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Warm up the strategy using historical candles."""
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                state = self._get_state(symbol, timeframe)

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    count=max(
                        self._donchian_period * 3,
                        self._atr_period * 3,
                        100,
                    ),
                )

                for candle in candles:
                    self._update_state(
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
        """Release strategy state."""
        self._states.clear()

    async def on_candle(
        self,
        candle,
    ) -> TradingSignal | None:
        """Process a completed candle."""
        symbol = candle.symbol
        timeframe = Timeframe(candle.timeframe)

        state = self._get_state(symbol, timeframe)

        previous_upper = self._channel_high(state)
        previous_lower = self._channel_low(state)

        atr_value = self._update_state(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        if previous_upper is None or previous_lower is None:
            return None

        if atr_value <= 0:
            return None

        timestamp = self._normalize_timestamp(candle.timestamp)

        if state.last_signal_timestamp == timestamp:
            return None

        close = float(candle.close)

        direction: SignalDirection | None = None
        reason: str | None = None

        if close > previous_upper:
            direction = SignalDirection.LONG
            reason = (
                "Price broke above the Donchian "
                f"{self._donchian_period}-period upper channel"
            )

        elif close < previous_lower:
            direction = SignalDirection.SHORT
            reason = (
                "Price broke below the Donchian "
                f"{self._donchian_period}-period lower channel"
            )

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
                "donchian_period": self._donchian_period,
                "upper_channel": previous_upper,
                "lower_channel": previous_lower,
                "atr": atr_value,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
            },
        )

    def _get_state(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> _IndicatorState:
        """Get or create isolated state."""
        key = (symbol, timeframe)

        state = self._states.get(key)

        if state is None:
            state = _IndicatorState(
                highs=deque(maxlen=self._donchian_period),
                lows=deque(maxlen=self._donchian_period),
                atr=ATR(self._atr_period),
            )
            self._states[key] = state

        return state

    def _update_state(
        self,
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ) -> float:
        """Update channel and ATR state."""
        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=float(close),
        )

        state.highs.append(float(high))
        state.lows.append(float(low))
        state.previous_close = float(close)

        return atr_value

    @staticmethod
    def _channel_high(
        state: _IndicatorState,
    ) -> float | None:
        """Return the current stored upper channel."""
        if not state.highs:
            return None

        return max(state.highs)

    @staticmethod
    def _channel_low(
        state: _IndicatorState,
    ) -> float | None:
        """Return the current stored lower channel."""
        if not state.lows:
            return None

        return min(state.lows)

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        """Normalize timestamp to timezone-aware UTC."""
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)
