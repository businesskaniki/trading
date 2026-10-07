"""MACD trend-following strategy with ATR-based risk management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.market_data.models import MarketCandle
from strategies.core.base import (
    BaseStrategy,
    StrategyConfig,
    StrategyDefinition,
)
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
    previous_atr: float | None = None

    last_signal_timestamp: datetime | None = None


@register_strategy("macd_trend")
class MACDTrendStrategy(BaseStrategy):
    """
    MACD trend-following strategy.

    Long:
        MACD crosses above the signal line.

    Short:
        MACD crosses below the signal line.

    Stop-loss and take-profit are calculated using ATR from
    the previous completed candle so that the signal candle
    does not determine its own risk distance.
    """

    definition = StrategyDefinition(
        name="macd_trend",
        version="1.1.0",
        description=(
            "MACD trend-following strategy with "
            "ATR-based stop-loss and take-profit."
        ),
        author="AQE",
        tags=(
            "trend",
            "macd",
            "atr",
            "crossover",
        ),
    )

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
        config: StrategyConfig,
        context: StrategyContext,
    ) -> None:
        super().__init__(
            config=config,
            context=context,
        )

        parameters = {
            **self.DEFAULT_PARAMETERS,
            **config.parameters,
        }

        self._fast_period = int(
            parameters["fast_period"]
        )

        self._slow_period = int(
            parameters["slow_period"]
        )

        self._signal_period = int(
            parameters["signal_period"]
        )

        self._atr_period = int(
            parameters["atr_period"]
        )

        self._stop_loss_atr = float(
            parameters["stop_loss_atr"]
        )

        self._take_profit_atr = float(
            parameters["take_profit_atr"]
        )

        self._confidence = float(
            parameters["confidence"]
        )

        if self._fast_period <= 0:
            raise ValueError(
                "fast_period must be greater than zero."
            )

        if self._slow_period <= 0:
            raise ValueError(
                "slow_period must be greater than zero."
            )

        if self._signal_period <= 0:
            raise ValueError(
                "signal_period must be greater than zero."
            )

        if self._atr_period <= 0:
            raise ValueError(
                "atr_period must be greater than zero."
            )

        if self._fast_period >= self._slow_period:
            raise ValueError(
                "fast_period must be smaller than slow_period."
            )

        if self._stop_loss_atr <= 0:
            raise ValueError(
                "stop_loss_atr must be greater than zero."
            )

        if self._take_profit_atr <= 0:
            raise ValueError(
                "take_profit_atr must be greater than zero."
            )

        if not 0.0 <= self._confidence <= 1.0:
            raise ValueError(
                "confidence must be between 0 and 1."
            )

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Warm up indicators using historical candles."""

        for symbol in self.symbols:
            for timeframe_name in self.timeframes:
                timeframe = Timeframe(
                    timeframe_name.strip().upper()
                )

                state = self._get_state(
                    symbol,
                    timeframe,
                )

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

                # Indicator state must always be constructed
                # in chronological order.
                candles = sorted(
                    candles,
                    key=lambda candle: candle.datetime,
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
        candle: MarketCandle,
    ) -> TradingSignal | None:
        """Process a completed candle."""

        symbol = candle.symbol

        timeframe = Timeframe(
            str(candle.timeframe).strip().upper()
        )

        state = self._get_state(
            symbol,
            timeframe,
        )

        # Preserve previous values before processing the
        # current completed candle.
        previous_macd = state.previous_macd
        previous_signal = state.previous_signal
        previous_atr = state.previous_atr

        macd_value, current_atr = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        if (
            previous_macd is None
            or previous_signal is None
        ):
            return None

        if previous_atr is None or previous_atr <= 0:
            return None

        if current_atr <= 0:
            return None

        # Store the current MACD values for the next candle.
        state.previous_macd = macd_value.macd
        state.previous_signal = macd_value.signal

        timestamp = candle.datetime

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # --------------------------------------------------------------
        # Bullish MACD crossover
        # --------------------------------------------------------------

        if (
            previous_macd <= previous_signal
            and macd_value.macd > macd_value.signal
        ):
            direction = SignalDirection.LONG
            reason = (
                "MACD crossed above the signal line"
            )

        # --------------------------------------------------------------
        # Bearish MACD crossover
        # --------------------------------------------------------------

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

        entry_price = Decimal(
            str(candle.close)
        )

        # Use the ATR from the previous completed candle.
        atr = Decimal(
            str(previous_atr)
        )

        stop_distance = (
            atr
            * Decimal(
                str(self._stop_loss_atr)
            )
        )

        target_distance = (
            atr
            * Decimal(
                str(self._take_profit_atr)
            )
        )

        if (
            stop_distance <= 0
            or target_distance <= 0
        ):
            return None

        if direction is SignalDirection.LONG:
            stop_loss = (
                entry_price - stop_distance
            )

            take_profit = (
                entry_price + target_distance
            )

        else:
            stop_loss = (
                entry_price + stop_distance
            )

            take_profit = (
                entry_price - target_distance
            )

        reward_distance = abs(
            take_profit - entry_price
        )

        risk_distance = abs(
            entry_price - stop_loss
        )

        if risk_distance <= 0:
            return None

        reward_risk = (
            reward_distance / risk_distance
        )

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
                "strategy_mode": self.mode.value,
                "macd": macd_value.macd,
                "signal": macd_value.signal,
                "histogram": macd_value.histogram,
                "previous_macd": previous_macd,
                "previous_signal": previous_signal,
                "atr": current_atr,
                "trade_atr": previous_atr,
                "fast_period": self._fast_period,
                "slow_period": self._slow_period,
                "signal_period": self._signal_period,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
                "reward_risk": float(reward_risk),
            },
        )

    def _get_state(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> _IndicatorState:
        """Get or create isolated indicator state."""

        key = (
            symbol,
            timeframe,
        )

        state = self._states.get(key)

        if state is None:
            state = _IndicatorState(
                macd=MACD(
                    fast_period=self._fast_period,
                    slow_period=self._slow_period,
                    signal_period=self._signal_period,
                ),
                atr=ATR(
                    self._atr_period
                ),
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

        macd_value = state.macd.update(
            float(close)
        )

        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=float(close),
        )

        if atr_value is not None:
            state.previous_atr = float(
                atr_value
            )

        return (
            macd_value,
            atr_value,
        )


__all__ = [
    "MACDTrendStrategy",
]