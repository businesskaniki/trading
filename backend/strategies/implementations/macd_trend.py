"""MACD trend-following strategy with ATR-based risk management."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

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
    """Indicator and candle state for one symbol/timeframe pair."""

    macd: MACD
    atr: ATR

    previous_macd: float | None = None
    previous_signal: float | None = None
    latest_atr: float | None = None

    last_candle_time: datetime | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("macd_trend")
class MACDTrendStrategy(BaseStrategy):
    """MACD trend-following strategy with ATR-based stops and targets.

    Long entries occur when MACD crosses above its signal line. Short
    entries occur when MACD crosses below its signal line.

    Stop-loss and take-profit distances use ATR from the previous
    completed candle. Historical initialization is mode-aware so that
    replay does not load candles from outside its chronological feed.
    """

    definition = StrategyDefinition(
        name="macd_trend",
        version="1.1.0",
        description=(
            "MACD trend-following strategy with "
            "ATR-based stop-loss and take-profit."
        ),
        author="AQE",
        tags=("trend", "macd", "atr", "crossover"),
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
        super().__init__(config=config, context=context)

        configured_parameters = config.parameters or {}
        unknown = set(configured_parameters) - set(self.DEFAULT_PARAMETERS)
        if unknown:
            raise ValueError(
                f"Unknown macd_trend parameters: {sorted(unknown)}"
            )

        parameters = {
            **self.DEFAULT_PARAMETERS,
            **configured_parameters,
        }

        self._fast_period = int(parameters["fast_period"])
        self._slow_period = int(parameters["slow_period"])
        self._signal_period = int(parameters["signal_period"])
        self._atr_period = int(parameters["atr_period"])
        self._stop_loss_atr = float(parameters["stop_loss_atr"])
        self._take_profit_atr = float(parameters["take_profit_atr"])
        self._confidence = float(parameters["confidence"])

        if self._fast_period <= 0:
            raise ValueError("fast_period must be greater than zero.")
        if self._slow_period <= 0:
            raise ValueError("slow_period must be greater than zero.")
        if self._signal_period <= 0:
            raise ValueError("signal_period must be greater than zero.")
        if self._atr_period <= 0:
            raise ValueError("atr_period must be greater than zero.")
        if self._fast_period >= self._slow_period:
            raise ValueError("fast_period must be smaller than slow_period.")

        finite_parameters = {
            "stop_loss_atr": self._stop_loss_atr,
            "take_profit_atr": self._take_profit_atr,
            "confidence": self._confidence,
        }
        for name, value in finite_parameters.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite.")

        if self._stop_loss_atr <= 0:
            raise ValueError("stop_loss_atr must be greater than zero.")
        if self._take_profit_atr <= 0:
            raise ValueError("take_profit_atr must be greater than zero.")
        if not 0.0 <= self._confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1.")

        self._states: dict[tuple[str, Timeframe], _IndicatorState] = {}

    def _mode_name(self) -> str:
        """Resolve the configured strategy/runtime mode defensively."""

        mode = getattr(self.config, "mode", None)
        if mode is None:
            mode = getattr(self.context, "mode", None)
        if mode is None:
            # Prefer historical-safe behavior when the mode is unknown.
            return "BACKTEST"

        value = getattr(mode, "value", mode)
        return str(value).strip().upper().rsplit(".", 1)[-1]

    def _is_historical_mode(self) -> bool:
        """Return whether initialization must respect a historical timeline."""

        return self._mode_name() in {"BACKTEST", "REPLAY"}

    async def on_initialize(self) -> None:
        """Initialize indicator state without violating simulation chronology."""

        self._states.clear()
        mode = self._mode_name()

        for symbol in self.symbols:
            for timeframe_name in self.timeframes:
                timeframe = Timeframe(str(timeframe_name).strip().upper())
                state = self._get_state(symbol, timeframe)

                # Replay must warm up from its own chronological candle feed.
                if mode == "REPLAY":
                    continue

                # In BACKTEST mode, the configured market-data view must
                # expose only candles strictly before the test start. This
                # is the same historical-view contract used by Bollinger.
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

                for candle in sorted(candles, key=lambda item: item.datetime):
                    if (
                        state.last_candle_time is not None
                        and candle.datetime <= state.last_candle_time
                    ):
                        continue

                    macd_value, _ = self._update_indicators(
                        state,
                        candle.high,
                        candle.low,
                        candle.close,
                    )
                    state.last_candle_time = candle.datetime

                    if self._macd_value_is_valid(macd_value):
                        state.previous_macd = float(macd_value.macd)
                        state.previous_signal = float(macd_value.signal)

    async def on_start(self) -> None:
        """Start the strategy."""

        return None

    async def on_stop(self) -> None:
        """Stop the strategy."""

        return None

    async def on_shutdown(self) -> None:
        """Release per-symbol indicator state."""

        self._states.clear()

    async def on_candle(
        self,
        candle: MarketCandle,
    ) -> TradingSignal | None:
        """Process a completed candle and optionally emit a crossover signal."""

        symbol = candle.symbol
        timeframe = Timeframe(str(candle.timeframe).strip().upper())
        timestamp = candle.datetime

        state = self._get_state(symbol, timeframe)

        # Match the defensive timestamp handling of Bollinger: duplicate or
        # out-of-order candles must not advance incremental indicators.
        if (
            state.last_candle_time is not None
            and timestamp <= state.last_candle_time
        ):
            return None
        state.last_candle_time = timestamp

        # Capture previous values before processing this candle. ATR is
        # updated below, but the trade uses the value from the prior candle.
        previous_macd = state.previous_macd
        previous_signal = state.previous_signal
        atr_before = state.latest_atr

        macd_value, current_atr = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        if not self._macd_value_is_valid(macd_value):
            return None

        current_macd = float(macd_value.macd)
        current_signal = float(macd_value.signal)

        # Advance the state on every valid MACD candle, even if ATR is not
        # ready yet. Otherwise a later candle could compare against stale data.
        state.previous_macd = current_macd
        state.previous_signal = current_signal

        # The first valid MACD value establishes a baseline, not a crossover.
        if previous_macd is None or previous_signal is None:
            return None

        if (
            atr_before is None
            or not math.isfinite(atr_before)
            or atr_before <= 0
        ):
            return None

        if (
            current_atr is None
            or not math.isfinite(float(current_atr))
            or float(current_atr) <= 0
        ):
            return None

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # Bullish crossover.
        if previous_macd <= previous_signal and current_macd > current_signal:
            direction = SignalDirection.LONG
            reason = "MACD crossed above the signal line"

        # Bearish crossover.
        elif previous_macd >= previous_signal and current_macd < current_signal:
            direction = SignalDirection.SHORT
            reason = "MACD crossed below the signal line"

        if direction is None:
            return None

        entry_price = Decimal(str(candle.close))
        atr = Decimal(str(atr_before))
        stop_distance = atr * Decimal(str(self._stop_loss_atr))
        target_distance = atr * Decimal(str(self._take_profit_atr))

        if (
            not stop_distance.is_finite()
            or not target_distance.is_finite()
            or stop_distance <= 0
            or target_distance <= 0
        ):
            return None

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + target_distance
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - target_distance

        if not all(
            value.is_finite()
            for value in (entry_price, stop_loss, take_profit)
        ):
            return None

        reward_distance = abs(take_profit - entry_price)
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance <= 0:
            return None

        reward_risk = reward_distance / risk_distance
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
                "macd": current_macd,
                "signal": current_signal,
                "histogram": float(macd_value.histogram),
                "previous_macd": previous_macd,
                "previous_signal": previous_signal,
                "atr": float(current_atr),
                "trade_atr": atr_before,
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
        """Get or create isolated state for one symbol/timeframe pair."""

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
    def _macd_value_is_valid(value: Any) -> bool:
        """Return True only if MACD, signal, and histogram are finite."""

        if value is None:
            return False

        try:
            values = (
                float(value.macd),
                float(value.signal),
                float(value.histogram),
            )
        except (AttributeError, TypeError, ValueError):
            return False

        return all(math.isfinite(item) for item in values)

    @staticmethod
    def _update_indicators(
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ) -> tuple[Any, float | None]:
        """Update MACD and ATR using one completed OHLC candle."""

        high_value = float(high)
        low_value = float(low)
        close_value = float(close)

        if not all(
            math.isfinite(value)
            for value in (high_value, low_value, close_value)
        ):
            raise ValueError("Candle OHLC values must be finite.")

        if high_value < low_value:
            raise ValueError("Candle high cannot be below candle low.")

        macd_value = state.macd.update(close_value)
        atr_value = state.atr.update(
            high=high_value,
            low=low_value,
            close=close_value,
        )

        if atr_value is not None:
            atr_float = float(atr_value)
            if math.isfinite(atr_float) and atr_float >= 0:
                state.latest_atr = atr_float

        return macd_value, state.latest_atr


__all__ = ["MACDTrendStrategy"]
