
"""RSI mean-reversion strategy with ATR risk levels and trend filtering."""

from __future__ import annotations

from dataclasses import dataclass, field
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
from strategies.indicators import ATR, RSI


@dataclass
class _IndicatorState:
    """Independent indicator and signal state per symbol/timeframe."""

    rsi: RSI
    atr: ATR

    previous_rsi: float | None = None
    previous_atr: float | None = None

    trend_ema: float | None = None
    trend_ema_history: list[float] = field(default_factory=list)
    trend_observations: int = 0

    bars_processed: int = 0
    last_signal_bar_index: int | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("rsi_reversal")
class RSIReversalStrategy(BaseStrategy):
    """
    RSI reversal with a directional trend-strength safeguard.

    Long:
        RSI recovers above the oversold threshold and the EMA slope
        is not falling beyond the configured ATR-normalized tolerance.

    Short:
        RSI falls below the overbought threshold and the EMA slope
        is not rising beyond the configured ATR-normalized tolerance.

    Risk:
        Stop-loss and take-profit distances are derived from the
        previous completed candle's ATR.

    Cooldown:
        Signals on the same symbol/timeframe are spaced apart by
        a configurable number of processed candles.
    """

    definition = StrategyDefinition(
        name="rsi_reversal",
        version="2.1.0",
        description=(
            "RSI mean-reversion strategy with ATR risk levels, "
            "EMA-slope filtering, and signal cooldown."
        ),
        author="AQE",
        tags=(
            "mean-reversion",
            "rsi",
            "atr",
            "trend-filter",
            "reversal",
        ),
    )

    DEFAULT_PARAMETERS = {
        "rsi_period": 14,
        "atr_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
        "stop_loss_atr": 1.0,
        "take_profit_atr": 1.5,
        "confidence": 0.70,

        # Trend filter.
        "trend_filter_enabled": True,
        "trend_ema_period": 50,
        "trend_slope_lookback": 5,

        # Maximum adverse EMA movement tolerated, expressed as
        # a multiple of the previous completed candle's ATR.
        "trend_slope_tolerance_atr": 0.05,

        # Minimum signal spacing per symbol/timeframe.
        # Zero disables the cooldown.
        "cooldown_bars": 4,
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

        self._rsi_period = int(parameters["rsi_period"])
        self._atr_period = int(parameters["atr_period"])

        self._oversold = float(parameters["oversold"])
        self._overbought = float(parameters["overbought"])

        self._stop_loss_atr = float(
            parameters["stop_loss_atr"]
        )
        self._take_profit_atr = float(
            parameters["take_profit_atr"]
        )
        self._confidence = float(parameters["confidence"])

        self._trend_filter_enabled = parameters[
            "trend_filter_enabled"
        ]

        if not isinstance(self._trend_filter_enabled, bool):
            raise ValueError(
                "trend_filter_enabled must be a boolean."
            )

        self._trend_ema_period = int(
            parameters["trend_ema_period"]
        )
        self._trend_slope_lookback = int(
            parameters["trend_slope_lookback"]
        )
        self._trend_slope_tolerance_atr = float(
            parameters["trend_slope_tolerance_atr"]
        )
        self._cooldown_bars = int(parameters["cooldown_bars"])

        if self._rsi_period <= 0:
            raise ValueError(
                "rsi_period must be greater than zero."
            )

        if self._atr_period <= 0:
            raise ValueError(
                "atr_period must be greater than zero."
            )

        if not 0.0 <= self._oversold <= 100.0:
            raise ValueError(
                "oversold must be between 0 and 100."
            )

        if not 0.0 <= self._overbought <= 100.0:
            raise ValueError(
                "overbought must be between 0 and 100."
            )

        if self._oversold >= self._overbought:
            raise ValueError(
                "oversold must be smaller than overbought."
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

        if self._trend_ema_period <= 0:
            raise ValueError(
                "trend_ema_period must be greater than zero."
            )

        if self._trend_slope_lookback <= 0:
            raise ValueError(
                "trend_slope_lookback must be greater than zero."
            )

        if self._trend_slope_tolerance_atr < 0:
            raise ValueError(
                "trend_slope_tolerance_atr cannot be negative."
            )

        if self._cooldown_bars < 0:
            raise ValueError(
                "cooldown_bars cannot be negative."
            )

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Initialize indicators from available historical candles."""

        for symbol in self.symbols:
            for timeframe_name in self.timeframes:
                timeframe = Timeframe(
                    timeframe_name.strip().upper()
                )

                state = self._get_state(symbol, timeframe)

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    count=max(
                        self._rsi_period * 3,
                        self._atr_period * 3,
                        self._trend_ema_period
                        + self._trend_slope_lookback
                        + 10,
                        100,
                    ),
                )

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
        """Process a completed candle and optionally emit an entry."""

        symbol = candle.symbol

        timeframe = Timeframe(
            str(candle.timeframe).strip().upper()
        )

        state = self._get_state(symbol, timeframe)

        # Preserve ATR from the previously processed candle for
        # risk distances and slope normalization.
        previous_atr = state.previous_atr

        current_rsi, current_atr = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_rsi = state.previous_rsi
        state.previous_rsi = current_rsi

        if previous_atr is None or previous_atr <= 0:
            return None

        if previous_rsi is None:
            return None

        if not 0.0 <= current_rsi <= 100.0:
            return None

        timestamp = candle.datetime

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # RSI must cross back out of an extreme reading.
        if (
            previous_rsi <= self._oversold
            and current_rsi > self._oversold
        ):
            direction = SignalDirection.LONG
            reason = (
                f"RSI recovered above oversold level "
                f"({self._oversold:.2f})"
            )

        elif (
            previous_rsi >= self._overbought
            and current_rsi < self._overbought
        ):
            direction = SignalDirection.SHORT
            reason = (
                f"RSI fell below overbought level "
                f"({self._overbought:.2f})"
            )

        if direction is None:
            return None

        # Avoid entering when EMA direction strongly contradicts
        # the proposed reversal.
        trend_slope = self._get_trend_slope(state)

        if self._trend_filter_enabled:
            if not self._trend_allows(
                direction=direction,
                state=state,
                reference_atr=previous_atr,
            ):
                return None

        # Cooldown is local to each symbol/timeframe. It measures
        # spacing between emitted signals, not position exit times.
        if (
            self._cooldown_bars > 0
            and state.last_signal_bar_index is not None
            and (
                state.bars_processed
                - state.last_signal_bar_index
            ) < self._cooldown_bars
        ):
            return None

        entry_price = Decimal(str(candle.close))
        atr = Decimal(str(previous_atr))

        stop_distance = atr * Decimal(
            str(self._stop_loss_atr)
        )
        target_distance = atr * Decimal(
            str(self._take_profit_atr)
        )

        if stop_distance <= 0 or target_distance <= 0:
            return None

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + target_distance
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - target_distance

        risk_distance = abs(entry_price - stop_loss)
        reward_distance = abs(take_profit - entry_price)

        if risk_distance <= 0:
            return None

        reward_risk = reward_distance / risk_distance

        state.last_signal_timestamp = timestamp
        state.last_signal_bar_index = state.bars_processed

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
                "rsi": current_rsi,
                "previous_rsi": previous_rsi,
                "atr": current_atr,
                "trade_atr": previous_atr,
                "oversold": self._oversold,
                "overbought": self._overbought,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
                "reward_risk": float(reward_risk),
                "trend_filter_enabled": self._trend_filter_enabled,
                "trend_ema_period": self._trend_ema_period,
                "trend_slope_lookback": self._trend_slope_lookback,
                "trend_slope_tolerance_atr": (
                    self._trend_slope_tolerance_atr
                ),
                "trend_ema": state.trend_ema,
                "trend_ema_slope": trend_slope,
                "cooldown_bars": self._cooldown_bars,
            },
        )

    def _trend_allows(
        self,
        *,
        direction: SignalDirection,
        state: _IndicatorState,
        reference_atr: float,
    ) -> bool:
        """Return whether EMA slope is acceptable for the direction."""

        slope = self._get_trend_slope(state)

        # Do not trade before enough trend history is available.
        if slope is None:
            return False

        tolerance = (
            reference_atr * self._trend_slope_tolerance_atr
        )

        if direction is SignalDirection.LONG:
            return slope >= -tolerance

        if direction is SignalDirection.SHORT:
            return slope <= tolerance

        return False

    def _get_trend_slope(
        self,
        state: _IndicatorState,
    ) -> float | None:
        """Return the EMA change across the configured lookback."""

        required_observations = (
            self._trend_ema_period
        )

        required_history = (
            self._trend_slope_lookback + 1
        )

        if state.trend_observations < required_observations:
            return None

        if len(state.trend_ema_history) < required_history:
            return None

        return (
            state.trend_ema_history[-1]
            - state.trend_ema_history[0]
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

    def _update_indicators(
        self,
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ) -> tuple[float, float]:
        """Update RSI, ATR, and trend EMA from one candle."""

        close_value = float(close)

        rsi_value = state.rsi.update(close_value)

        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=close_value,
        )

        if atr_value is not None:
            state.previous_atr = float(atr_value)

        # Incremental EMA avoids requiring another indicator dependency.
        alpha = 2.0 / (self._trend_ema_period + 1.0)

        if state.trend_ema is None:
            state.trend_ema = close_value
        else:
            state.trend_ema += alpha * (
                close_value - state.trend_ema
            )

        state.trend_observations += 1
        state.bars_processed += 1

        state.trend_ema_history.append(state.trend_ema)

        max_history = self._trend_slope_lookback + 1

        if len(state.trend_ema_history) > max_history:
            del state.trend_ema_history[:-max_history]

        return (
            rsi_value,
            atr_value,
        )


__all__ = [
    "RSIReversalStrategy",
]
