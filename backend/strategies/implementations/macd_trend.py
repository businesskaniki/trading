
"""MACD trend-following strategy with ATR-based risk management."""

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
from strategies.indicators import ATR, MACD


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    macd: MACD
    atr: ATR
    previous_macd: float | None = None
    previous_signal: float | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("macd_trend")
class MACDTrendStrategy(BaseStrategy):
    """
    MACD trend-following strategy.

    Long:
        MACD crosses above the signal line.

    Short:
        MACD crosses below the signal line.

    Stop-loss and take-profit are calculated using ATR.
    """

    DEFAULT_PARAMETERS = {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
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

        self._fast_period = int(parameters["fast_period"])
        self._slow_period = int(parameters["slow_period"])
        self._signal_period = int(parameters["signal_period"])
        self._atr_period = int(parameters["atr_period"])

        self._stop_loss_atr = float(
            parameters["stop_loss_atr"]
        )
        self._take_profit_atr = float(
            parameters["take_profit_atr"]
        )
        self._confidence = float(
            parameters["confidence"]
        )

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
                        self._slow_period * 3,
                        self._signal_period * 3,
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

        macd_value, atr_value = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_macd = state.previous_macd
        previous_signal = state.previous_signal

        state.previous_macd = macd_value.macd
        state.previous_signal = macd_value.signal

        if previous_macd is None or previous_signal is None:
            return None

        if atr_value <= 0:
            return None

        timestamp = self._normalize_timestamp(
            candle.timestamp
        )

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # MACD crosses above signal line.
        if (
            previous_macd <= previous_signal
            and macd_value.macd > macd_value.signal
        ):
            direction = SignalDirection.LONG
            reason = (
                "MACD crossed above the signal line"
            )

        # MACD crosses below signal line.
        elif (
            previous_macd >= previous_signal
            and macd_value.macd < macd_value.signal
        ):
            direction = SignalDirection.SHORT
            reason = (
                "MACD crossed below the signal line"
            )

        if direction is None:
            return None

        entry_price = Decimal(str(candle.close))
        atr = Decimal(str(atr_value))

        stop_distance = (
            atr * Decimal(str(self._stop_loss_atr))
        )
        target_distance = (
            atr * Decimal(str(self._take_profit_atr))
        )

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
                "macd": macd_value.macd,
                "signal": macd_value.signal,
                "histogram": macd_value.histogram,
                "previous_macd": previous_macd,
                "previous_signal": previous_signal,
                "atr": atr_value,
                "fast_period": self._fast_period,
                "slow_period": self._slow_period,
                "signal_period": self._signal_period,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
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
                macd=MACD(
                    fast_period=self._fast_period,
                    slow_period=self._slow_period,
                    signal_period=self._signal_period,
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
        """Update MACD and ATR from one candle."""
        macd_value = state.macd.update(float(close))

        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=float(close),
        )

        return macd_value, atr_value

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        """Normalize timestamp to timezone-aware UTC."""
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)