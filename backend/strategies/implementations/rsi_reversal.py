"""RSI mean-reversion strategy with ATR-based risk levels."""

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
from strategies.core.signal import TradingSignal
from strategies.core.registry import register_strategy
from strategies.indicators import ATR, RSI


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    rsi: RSI
    atr: ATR
    previous_rsi: float | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("rsi_reversal")
class RSIReversalStrategy(BaseStrategy):
    """
    RSI mean-reversion strategy.

    Long:
        RSI crosses back above the oversold level.

    Short:
        RSI crosses back below the overbought level.

    Stop-loss and take-profit are calculated using ATR.
    """

    DEFAULT_PARAMETERS = {
        "rsi_period": 14,
        "atr_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
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

        self._rsi_period = int(parameters["rsi_period"])
        self._atr_period = int(parameters["atr_period"])
        self._oversold = float(parameters["oversold"])
        self._overbought = float(parameters["overbought"])
        self._stop_loss_atr = float(parameters["stop_loss_atr"])
        self._take_profit_atr = float(parameters["take_profit_atr"])
        self._confidence = float(parameters["confidence"])

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Initialize indicator state and warm up from historical candles."""
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                state = self._get_state(symbol, timeframe)

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    count=max(
                        self._rsi_period * 3,
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
        """Release strategy resources."""
        self._states.clear()

    async def on_candle(
        self,
        candle,
    ) -> TradingSignal | None:
        """Process a completed candle."""
        symbol = candle.symbol
        timeframe = Timeframe(candle.timeframe)

        state = self._get_state(symbol, timeframe)

        current_rsi, current_atr = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_rsi = state.previous_rsi
        state.previous_rsi = current_rsi

        if previous_rsi is None:
            return None

        if current_atr <= 0:
            return None

        timestamp = self._normalize_timestamp(candle.timestamp)

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # Oversold -> recovery above oversold = LONG.
        if previous_rsi <= self._oversold and current_rsi > self._oversold:
            direction = SignalDirection.LONG
            reason = f"RSI recovered above oversold level " f"({self._oversold:.2f})"

        # Overbought -> decline below overbought = SHORT.
        elif previous_rsi >= self._overbought and current_rsi < self._overbought:
            direction = SignalDirection.SHORT
            reason = f"RSI fell below overbought level " f"({self._overbought:.2f})"

        if direction is None:
            return None

        entry_price = Decimal(str(candle.close))
        atr = Decimal(str(current_atr))

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
                "rsi": current_rsi,
                "previous_rsi": previous_rsi,
                "atr": current_atr,
                "oversold": self._oversold,
                "overbought": self._overbought,
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
                rsi=RSI(self._rsi_period),
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
    ) -> tuple[float, float]:
        """Update RSI and ATR from one candle."""
        rsi_value = state.rsi.update(float(close))
        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=float(close),
        )

        return rsi_value, atr_value

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        """Normalize timestamp to timezone-aware UTC."""
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)
