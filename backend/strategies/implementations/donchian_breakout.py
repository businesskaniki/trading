"""Donchian Channel breakout strategy with trend and volatility filters."""

from __future__ import annotations

from collections import deque
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
from strategies.indicators import ATR


@dataclass
class _EMAState:
    """Incremental EMA state."""

    period: int
    value: float | None = None
    previous_value: float | None = None

    def update(
        self,
        price: float,
    ) -> float:
        """
        Update the EMA with a completed candle close.

        The first observed close seeds the EMA. The strategy supplies
        sufficient historical warm-up candles so the resulting value
        is stable before live/backtest signal generation begins.
        """

        price = float(price)

        if self.value is None:
            self.previous_value = None
            self.value = price
            return self.value

        self.previous_value = self.value

        multiplier = 2.0 / (self.period + 1.0)

        self.value = price * multiplier + self.value * (1.0 - multiplier)

        return self.value

    @property
    def slope(self) -> float | None:
        """
        Return the most recent EMA slope.

        Positive means rising.
        Negative means falling.
        """

        if self.value is None or self.previous_value is None:
            return None

        return self.value - self.previous_value


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    highs: deque[float]
    lows: deque[float]

    atr: ATR

    fast_ema: _EMAState
    slow_ema: _EMAState

    previous_close: float | None = None
    previous_atr: float | None = None

    bars_since_signal: int | None = None
    last_signal_timestamp: datetime | None = None


@register_strategy("donchian_breakout")
class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel breakout strategy with trend confirmation,
    breakout-strength filtering, and cooldown.

    Long setup:

        close >
            previous Donchian upper channel
            + ATR breakout buffer

        AND fast EMA > slow EMA

        AND fast EMA is rising

    Short setup:

        close <
            previous Donchian lower channel
            - ATR breakout buffer

        AND fast EMA < slow EMA

        AND fast EMA is falling

    The current candle is excluded from the Donchian channel.

    The ATR from the previous completed candle is used for the
    trade's stop, target, and breakout buffer.

    A cooldown prevents repeated breakout entries in rapid succession,
    reducing whipsaw participation after a fresh signal.
    """

    definition = StrategyDefinition(
        name="donchian_breakout",
        version="1.2.0",
        description=(
            "Donchian Channel breakout strategy with "
            "EMA trend confirmation, ATR breakout filtering, "
            "and cooldown-based whipsaw control."
        ),
        author="AQE",
        tags=(
            "breakout",
            "donchian",
            "trend",
            "atr",
            "ema",
            "volatility",
        ),
    )

    DEFAULT_PARAMETERS = {
        # Donchian channel.
        "donchian_period": 20,
        # ATR risk model.
        "atr_period": 14,
        "stop_loss_atr": 1.5,
        "take_profit_atr": 3.0,
        # Trend confirmation.
        "fast_ema_period": 50,
        "slow_ema_period": 200,
        "require_ema_slope": True,
        # Breakout quality.
        #
        # The breakout must close this many ATRs beyond the
        # previous Donchian boundary.
        "breakout_buffer_atr": 0.10,
        # Prevent repeated entries immediately after a signal.
        "cooldown_bars": 4,
        # Signal confidence passed downstream to RiskEngine.
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

        self._donchian_period = int(
            parameters["donchian_period"],
        )

        self._atr_period = int(
            parameters["atr_period"],
        )

        self._stop_loss_atr = float(
            parameters["stop_loss_atr"],
        )

        self._take_profit_atr = float(
            parameters["take_profit_atr"],
        )

        self._fast_ema_period = int(
            parameters["fast_ema_period"],
        )

        self._slow_ema_period = int(
            parameters["slow_ema_period"],
        )

        self._require_ema_slope = bool(
            parameters["require_ema_slope"],
        )

        self._breakout_buffer_atr = float(
            parameters["breakout_buffer_atr"],
        )

        self._cooldown_bars = int(
            parameters["cooldown_bars"],
        )

        self._confidence = float(
            parameters["confidence"],
        )

        # --------------------------------------------------------------
        # Configuration validation
        # --------------------------------------------------------------

        if self._donchian_period <= 0:
            raise ValueError(
                "donchian_period must be greater than zero.",
            )

        if self._atr_period <= 0:
            raise ValueError(
                "atr_period must be greater than zero.",
            )

        if self._stop_loss_atr <= 0:
            raise ValueError(
                "stop_loss_atr must be greater than zero.",
            )

        if self._take_profit_atr <= 0:
            raise ValueError(
                "take_profit_atr must be greater than zero.",
            )

        if self._fast_ema_period <= 0:
            raise ValueError(
                "fast_ema_period must be greater than zero.",
            )

        if self._slow_ema_period <= 0:
            raise ValueError(
                "slow_ema_period must be greater than zero.",
            )

        if self._fast_ema_period >= self._slow_ema_period:
            raise ValueError(
                "fast_ema_period must be smaller than " "slow_ema_period.",
            )

        if self._breakout_buffer_atr < 0:
            raise ValueError(
                "breakout_buffer_atr cannot be negative.",
            )

        if self._cooldown_bars < 0:
            raise ValueError(
                "cooldown_bars cannot be negative.",
            )

        if not 0.0 <= self._confidence <= 1.0:
            raise ValueError(
                "confidence must be between 0 and 1.",
            )

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def on_initialize(self) -> None:
        """
        Warm up the strategy using historical candles.

        Enough candles are loaded to establish:

            - Donchian channel
            - ATR
            - fast EMA
            - slow EMA

        The candles are always processed chronologically.
        """

        warmup_count = max(
            self._donchian_period * 3,
            self._atr_period * 3,
            self._slow_ema_period * 3,
            300,
        )

        for symbol in self.symbols:
            for timeframe_name in self.timeframes:
                timeframe = Timeframe(
                    timeframe_name.strip().upper(),
                )

                state = self._get_state(
                    symbol,
                    timeframe,
                )

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    count=warmup_count,
                )

                candles = sorted(
                    candles,
                    key=lambda candle: candle.datetime,
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

    # ==================================================================
    # CANDLE PROCESSING
    # ==================================================================

    async def on_candle(
        self,
        candle: MarketCandle,
    ) -> TradingSignal | None:
        """Process a completed candle."""

        symbol = candle.symbol

        timeframe = Timeframe(
            str(candle.timeframe).strip().upper(),
        )

        state = self._get_state(
            symbol,
            timeframe,
        )

        # --------------------------------------------------------------
        # Capture indicator values from the PREVIOUS completed candle.
        #
        # The current candle must not determine its own Donchian
        # channel, ATR-based trade risk, or trend state.
        # --------------------------------------------------------------

        previous_upper = self._channel_high(
            state,
        )

        previous_lower = self._channel_low(
            state,
        )

        previous_atr = state.previous_atr

        previous_fast_ema = state.fast_ema.value
        previous_slow_ema = state.slow_ema.value

        previous_fast_ema_slope = state.fast_ema.slope
        previous_slow_ema_slope = state.slow_ema.slope

        # --------------------------------------------------------------
        # Update state with the current completed candle.
        # --------------------------------------------------------------

        current_atr = self._update_state(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        # --------------------------------------------------------------
        # Basic indicator readiness.
        # --------------------------------------------------------------

        if previous_upper is None or previous_lower is None:
            return None

        if previous_atr is None or previous_atr <= 0:
            return None

        if current_atr <= 0:
            return None

        if previous_fast_ema is None or previous_slow_ema is None:
            return None

        # --------------------------------------------------------------
        # Cooldown.
        #
        # bars_since_signal is advanced by _update_state().
        # A signal is allowed only after the configured cooldown
        # has elapsed.
        # --------------------------------------------------------------

        if state.bars_since_signal is not None:
            if state.bars_since_signal < self._cooldown_bars:
                return None

        timestamp = candle.datetime

        # Never emit two signals for the same completed candle.
        if state.last_signal_timestamp == timestamp:
            return None

        close = float(candle.close)

        # --------------------------------------------------------------
        # Breakout buffer.
        #
        # The breakout needs to exceed the Donchian boundary by a
        # meaningful fraction of the previous ATR.
        # --------------------------------------------------------------

        atr = Decimal(
            str(previous_atr),
        )

        breakout_buffer = atr * Decimal(
            str(self._breakout_buffer_atr),
        )

        upper_breakout_level = (
            Decimal(
                str(previous_upper),
            )
            + breakout_buffer
        )

        lower_breakout_level = (
            Decimal(
                str(previous_lower),
            )
            - breakout_buffer
        )

        entry_price = Decimal(
            str(candle.close),
        )

        # --------------------------------------------------------------
        # Trend filter.
        #
        # Long:
        #     fast EMA > slow EMA
        #
        # Short:
        #     fast EMA < slow EMA
        #
        # Optional slope confirmation requires the fast EMA to move
        # in the direction of the proposed trade.
        # --------------------------------------------------------------

        trend_long = previous_fast_ema > previous_slow_ema

        trend_short = previous_fast_ema < previous_slow_ema

        slope_long = True
        slope_short = True

        if self._require_ema_slope:
            slope_long = (
                previous_fast_ema_slope is not None and previous_fast_ema_slope > 0
            )

            slope_short = (
                previous_fast_ema_slope is not None and previous_fast_ema_slope < 0
            )

        # --------------------------------------------------------------
        # Breakout detection.
        # --------------------------------------------------------------

        direction: SignalDirection | None = None
        reason: str | None = None

        if entry_price > upper_breakout_level and trend_long and slope_long:
            direction = SignalDirection.LONG

            reason = (
                "Price broke above the Donchian "
                f"{self._donchian_period}-period upper channel "
                "with ATR breakout confirmation and bullish "
                "EMA trend alignment."
            )

        elif entry_price < lower_breakout_level and trend_short and slope_short:
            direction = SignalDirection.SHORT

            reason = (
                "Price broke below the Donchian "
                f"{self._donchian_period}-period lower channel "
                "with ATR breakout confirmation and bearish "
                "EMA trend alignment."
            )

        if direction is None:
            return None

        # --------------------------------------------------------------
        # ATR-based risk.
        #
        # Use previous completed candle ATR.
        # --------------------------------------------------------------

        stop_distance = atr * Decimal(
            str(self._stop_loss_atr),
        )

        target_distance = atr * Decimal(
            str(self._take_profit_atr),
        )

        if stop_distance <= 0 or target_distance <= 0:
            return None

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance

            take_profit = entry_price + target_distance

        else:
            stop_loss = entry_price + stop_distance

            take_profit = entry_price - target_distance

        risk_distance = abs(
            entry_price - stop_loss,
        )

        reward_distance = abs(
            take_profit - entry_price,
        )

        if risk_distance <= 0:
            return None

        reward_risk = reward_distance / risk_distance

        # --------------------------------------------------------------
        # Breakout diagnostics.
        # --------------------------------------------------------------

        if direction is SignalDirection.LONG:
            breakout_distance = entry_price - Decimal(
                str(previous_upper),
            )
        else:
            breakout_distance = (
                Decimal(
                    str(previous_lower),
                )
                - entry_price
            )

        breakout_distance_atr = breakout_distance / atr if atr > 0 else Decimal("0")

        # --------------------------------------------------------------
        # Mark the signal.
        # --------------------------------------------------------------

        state.last_signal_timestamp = timestamp
        state.bars_since_signal = 0

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
                "atr": current_atr,
                "trade_atr": previous_atr,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
                "reward_risk": float(reward_risk),
                # Trend diagnostics.
                "fast_ema_period": self._fast_ema_period,
                "slow_ema_period": self._slow_ema_period,
                "fast_ema": previous_fast_ema,
                "slow_ema": previous_slow_ema,
                "fast_ema_slope": previous_fast_ema_slope,
                "slow_ema_slope": previous_slow_ema_slope,
                "trend_long": trend_long,
                "trend_short": trend_short,
                # Breakout diagnostics.
                "breakout_buffer_atr": self._breakout_buffer_atr,
                "breakout_buffer": float(breakout_buffer),
                "breakout_distance": float(
                    breakout_distance,
                ),
                "breakout_distance_atr": float(
                    breakout_distance_atr,
                ),
                # Cooldown diagnostics.
                "cooldown_bars": self._cooldown_bars,
            },
        )

    # ==================================================================
    # STATE
    # ==================================================================

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
                highs=deque(
                    maxlen=self._donchian_period,
                ),
                lows=deque(
                    maxlen=self._donchian_period,
                ),
                atr=ATR(
                    self._atr_period,
                ),
                fast_ema=_EMAState(
                    period=self._fast_ema_period,
                ),
                slow_ema=_EMAState(
                    period=self._slow_ema_period,
                ),
            )

            self._states[key] = state

        return state

    # ==================================================================
    # INDICATOR UPDATES
    # ==================================================================

    def _update_state(
        self,
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ) -> float:
        """
        Update Donchian, ATR, and EMA state.

        The resulting ATR and EMA values represent the current
        completed candle and are used as previous-candle values
        on the next candle.
        """

        close_float = float(close)

        atr_value = state.atr.update(
            high=float(high),
            low=float(low),
            close=close_float,
        )

        state.fast_ema.update(
            close_float,
        )

        state.slow_ema.update(
            close_float,
        )

        state.highs.append(
            float(high),
        )

        state.lows.append(
            float(low),
        )

        state.previous_close = close_float

        if atr_value is not None:
            state.previous_atr = float(
                atr_value,
            )

        # Advance cooldown after processing each completed candle.
        if state.bars_since_signal is not None:
            state.bars_since_signal += 1

        return atr_value

    # ==================================================================
    # DONCHIAN CHANNEL
    # ==================================================================

    @staticmethod
    def _channel_high(
        state: _IndicatorState,
    ) -> float | None:
        """
        Return the stored upper Donchian channel.

        The current candle is not present yet when this method is
        called from on_candle(), so the returned channel represents
        the previous completed candles only.
        """

        if len(state.highs) < 1:
            return None

        return max(
            state.highs,
        )

    @staticmethod
    def _channel_low(
        state: _IndicatorState,
    ) -> float | None:
        """
        Return the stored lower Donchian channel.

        The current candle is not present yet when this method is
        called from on_candle(), so the returned channel represents
        the previous completed candles only.
        """

        if len(state.lows) < 1:
            return None

        return min(
            state.lows,
        )


__all__ = [
    "DonchianBreakoutStrategy",
]
