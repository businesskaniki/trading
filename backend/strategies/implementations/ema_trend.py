"""EMA trend-following strategy for the AQE Strategy Engine."""

from __future__ import annotations

from dataclasses import dataclass

from app.events.market import MarketCandleEvent

from ..core.base import BaseStrategy, StrategyDefinition
from ..core.enums import (
    OrderType,
    SignalDirection,
    SignalType,
    Timeframe,
)
from ..core.exceptions import StrategyConfigurationError
from ..core.registry import register_strategy
from ..core.signal import TradingSignal


@dataclass(slots=True)
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    previous_ema_fast: float | None = None
    previous_ema_slow: float | None = None

    ema_fast: float | None = None
    ema_slow: float | None = None

    atr: float | None = None
    previous_close: float | None = None

    initialized: bool = False


@register_strategy("ema_trend")
class EMATrendStrategy(BaseStrategy):
    """
    EMA crossover trend-following strategy with ATR-based exits.

    LONG:
        previous EMA fast <= previous EMA slow
        current EMA fast > current EMA slow
        current close > current EMA slow

    SHORT:
        previous EMA fast >= previous EMA slow
        current EMA fast < current EMA slow
        current close < current EMA slow

    Risk levels are calculated from ATR:

        LONG:
            stop_loss   = entry - ATR * stop_loss_atr
            take_profit = entry + ATR * take_profit_atr

        SHORT:
            stop_loss   = entry + ATR * stop_loss_atr
            take_profit = entry - ATR * take_profit_atr

    The strategy generates trading intent only. Risk approval,
    position sizing, and order execution are handled downstream.
    """

    definition = StrategyDefinition(
        name="ema_trend",
        version="1.0.0",
        description=(
            "EMA crossover trend-following strategy with "
            "ATR-based stop-loss and take-profit."
        ),
        author="AQE",
        tags=[
            "trend",
            "ema",
            "atr",
            "crossover",
        ],
    )

    DEFAULT_FAST_PERIOD = 20
    DEFAULT_SLOW_PERIOD = 50
    DEFAULT_ATR_PERIOD = 14
    DEFAULT_STOP_LOSS_ATR = 1.5
    DEFAULT_TAKE_PROFIT_ATR = 3.0
    DEFAULT_CONFIDENCE = 0.70

    def __init__(self, *args, **kwargs) -> None:
        """Create the EMA trend strategy."""

        super().__init__(*args, **kwargs)

        self.fast_period = self._positive_int_parameter(
            "fast_period",
            self.DEFAULT_FAST_PERIOD,
        )

        self.slow_period = self._positive_int_parameter(
            "slow_period",
            self.DEFAULT_SLOW_PERIOD,
        )

        self.atr_period = self._positive_int_parameter(
            "atr_period",
            self.DEFAULT_ATR_PERIOD,
        )

        self.stop_loss_atr = self._positive_float_parameter(
            "stop_loss_atr",
            self.DEFAULT_STOP_LOSS_ATR,
        )

        self.take_profit_atr = self._positive_float_parameter(
            "take_profit_atr",
            self.DEFAULT_TAKE_PROFIT_ATR,
        )

        self.confidence = self._confidence_parameter(
            "confidence",
            self.DEFAULT_CONFIDENCE,
        )

        if self.fast_period >= self.slow_period:
            raise StrategyConfigurationError(
                "fast_period must be smaller than slow_period."
            )

        self._states: dict[
            tuple[str, str],
            _IndicatorState,
        ] = {}

        self._last_signal_candle: dict[
            tuple[str, str],
            int,
        ] = {}

    async def on_initialize(self) -> None:
        """
        Warm up indicator state from historical market data.

        Historical data is accessed only through StrategyContext.
        The strategy remains safe when no market-data provider is
        available.
        """

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                if timeframe == "TICK":
                    continue

                await self._warm_up(
                    symbol=symbol,
                    timeframe=timeframe,
                )

    async def on_stop(self) -> None:
        """Clear runtime indicator state."""

        self._states.clear()
        self._last_signal_candle.clear()

    async def on_candle(
        self,
        event: MarketCandleEvent,
    ) -> TradingSignal | None:
        """Process one normalized market candle."""

        candle = event.candle

        if not self.supports_candle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
        ):
            return None

        timeframe = candle.timeframe.upper()

        if timeframe == "TICK":
            return None

        key = (
            candle.symbol,
            timeframe,
        )

        state = self._states.setdefault(
            key,
            _IndicatorState(),
        )

        candle_open = float(candle.open)
        candle_high = float(candle.high)
        candle_low = float(candle.low)
        candle_close = float(candle.close)

        if candle_close <= 0:
            return None

        if candle_high < candle_low:
            return None

        if candle_open <= 0:
            return None

        # Capture the previous indicator state BEFORE updating it.
        previous_ema_fast = state.ema_fast
        previous_ema_slow = state.ema_slow

        self._update_indicators(
            state=state,
            high=candle_high,
            low=candle_low,
            close=candle_close,
        )

        if (
            previous_ema_fast is None
            or previous_ema_slow is None
            or state.ema_fast is None
            or state.ema_slow is None
            or state.atr is None
        ):
            return None

        if state.atr <= 0:
            return None

        if not state.initialized:
            state.initialized = True
            return None

        direction = self._detect_crossover(
            previous_ema_fast=previous_ema_fast,
            previous_ema_slow=previous_ema_slow,
            current_ema_fast=state.ema_fast,
            current_ema_slow=state.ema_slow,
            close=candle_close,
        )

        if direction is None:
            return None

        candle_timestamp = self._timestamp_value(
            candle.timestamp,
        )

        if self._last_signal_candle.get(key) == candle_timestamp:
            return None

        self._last_signal_candle[key] = candle_timestamp

        return self._build_signal(
            event=event,
            direction=direction,
            atr=state.atr,
        )

    async def _warm_up(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Load historical candles and initialize indicators."""

        candles = await self.context.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=self._warmup_count(),
        )

        if not candles:
            return

        ordered_candles = sorted(
            candles,
            key=lambda candle: self._timestamp_value(
                candle.timestamp,
            ),
        )

        state = _IndicatorState()

        for candle in ordered_candles:
            high = float(candle.high)
            low = float(candle.low)
            close = float(candle.close)

            if high < low or close <= 0:
                continue

            self._update_indicators(
                state=state,
                high=high,
                low=low,
                close=close,
            )

        if (
            state.ema_fast is not None
            and state.ema_slow is not None
            and state.atr is not None
        ):
            state.initialized = True

        self._states[
            (
                symbol,
                timeframe.upper(),
            )
        ] = state

    def _update_indicators(
        self,
        *,
        state: _IndicatorState,
        high: float,
        low: float,
        close: float,
    ) -> None:
        """Update EMA and ATR values using one candle."""

        previous_close = state.previous_close

        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        if state.ema_fast is None:
            state.ema_fast = close
        else:
            fast_alpha = 2.0 / (self.fast_period + 1.0)

            state.ema_fast = close * fast_alpha + state.ema_fast * (1.0 - fast_alpha)

        if state.ema_slow is None:
            state.ema_slow = close
        else:
            slow_alpha = 2.0 / (self.slow_period + 1.0)

            state.ema_slow = close * slow_alpha + state.ema_slow * (1.0 - slow_alpha)

        if state.atr is None:
            state.atr = true_range
        else:
            atr_alpha = 1.0 / self.atr_period

            state.atr = state.atr * (1.0 - atr_alpha) + true_range * atr_alpha

        state.previous_close = close

    @staticmethod
    def _detect_crossover(
        *,
        previous_ema_fast: float,
        previous_ema_slow: float,
        current_ema_fast: float,
        current_ema_slow: float,
        close: float,
    ) -> SignalDirection | None:
        """Detect a confirmed bullish or bearish EMA crossover."""

        bullish_cross = (
            previous_ema_fast <= previous_ema_slow
            and current_ema_fast > current_ema_slow
        )

        if bullish_cross and close > current_ema_slow:
            return SignalDirection.LONG

        bearish_cross = (
            previous_ema_fast >= previous_ema_slow
            and current_ema_fast < current_ema_slow
        )

        if bearish_cross and close < current_ema_slow:
            return SignalDirection.SHORT

        return None

    def _build_signal(
        self,
        *,
        event: MarketCandleEvent,
        direction: SignalDirection,
        atr: float,
    ) -> TradingSignal:
        """Create the normalized AQE trading signal."""

        candle = event.candle

        entry_price = float(candle.close)

        stop_distance = atr * self.stop_loss_atr

        take_profit_distance = atr * self.take_profit_atr

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance

            take_profit = entry_price + take_profit_distance

            reason = f"Bullish EMA crossover on " f"{candle.symbol} {candle.timeframe}."

        else:
            stop_loss = entry_price + stop_distance

            take_profit = entry_price - take_profit_distance

            reason = f"Bearish EMA crossover on " f"{candle.symbol} {candle.timeframe}."

        return TradingSignal(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            symbol=candle.symbol,
            timeframe=Timeframe(candle.timeframe),
            signal_type=SignalType.ENTRY,
            direction=direction,
            order_type=OrderType.MARKET,
            timestamp=self.context.now(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=self.confidence,
            reason=reason,
            metadata={
                "strategy_mode": self.mode.value,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "atr_period": self.atr_period,
                "atr": atr,
                "stop_loss_atr": self.stop_loss_atr,
                "take_profit_atr": self.take_profit_atr,
            },
        )

    def _warmup_count(self) -> int:
        """Return the historical candle count required for warm-up."""

        return max(
            self.slow_period * 3,
            self.atr_period * 3,
            100,
        )

    def _positive_int_parameter(
        self,
        name: str,
        default: int,
    ) -> int:
        """Read a positive integer strategy parameter."""

        value = self.context.parameter(
            name,
            default,
        )

        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be an integer."
            ) from exc

        if value <= 0:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be greater than zero."
            )

        return value

    def _positive_float_parameter(
        self,
        name: str,
        default: float,
    ) -> float:
        """Read a positive floating-point parameter."""

        value = self.context.parameter(
            name,
            default,
        )

        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be numeric."
            ) from exc

        if value <= 0:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be greater than zero."
            )

        return value

    def _confidence_parameter(
        self,
        name: str,
        default: float,
    ) -> float:
        """Read and validate signal confidence."""

        value = self.context.parameter(
            name,
            default,
        )

        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be numeric."
            ) from exc

        if not 0.0 <= value <= 1.0:
            raise StrategyConfigurationError(
                f"Strategy parameter '{name}' must be between 0 and 1."
            )

        return value

    @staticmethod
    def _timestamp_value(timestamp: object) -> int:
        """Convert supported timestamp values into integer seconds."""

        if hasattr(timestamp, "timestamp"):
            return int(timestamp.timestamp())

        return int(timestamp)
