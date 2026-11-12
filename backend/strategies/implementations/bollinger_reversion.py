"""Bollinger Band mean-reversion strategy with ATR risk and regime filtering."""

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
from strategies.indicators import ATR, BollingerBands


class _ADX:
    """Wilder ADX implementation without an additional dependency."""

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("ADX period must be at least 1.")

        self._period = period

        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._prev_close: float | None = None

        self._count = 0
        self._tr = 0.0
        self._plus_dm = 0.0
        self._minus_dm = 0.0

        self._dx_values: list[float] = []
        self._adx: float | None = None

    def update(
        self,
        high: float,
        low: float,
        close: float,
    ) -> float | None:
        """Update ADX using one completed OHLC candle."""

        if not all(math.isfinite(value) for value in (high, low, close)):
            raise ValueError("ADX input prices must be finite.")

        if high < low:
            raise ValueError("Candle high cannot be below candle low.")

        if self._prev_close is None:
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            return None

        # These values are initialized together with _prev_close.
        assert self._prev_high is not None
        assert self._prev_low is not None

        up_move = high - self._prev_high
        down_move = self._prev_low - low

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        true_range = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close

        self._count += 1
        period = self._period

        # Initial Wilder sums.
        if self._count <= period:
            self._tr += true_range
            self._plus_dm += plus_dm
            self._minus_dm += minus_dm

            if self._count < period:
                return None

        # Subsequent Wilder smoothing.
        else:
            self._tr = self._tr - self._tr / period + true_range
            self._plus_dm = self._plus_dm - self._plus_dm / period + plus_dm
            self._minus_dm = self._minus_dm - self._minus_dm / period + minus_dm

        if self._tr <= 0:
            dx = 0.0
        else:
            plus_di = 100.0 * self._plus_dm / self._tr
            minus_di = 100.0 * self._minus_dm / self._tr
            di_total = plus_di + minus_di

            dx = 100.0 * abs(plus_di - minus_di) / di_total if di_total > 0 else 0.0

        if self._adx is None:
            self._dx_values.append(dx)

            if len(self._dx_values) < period:
                return None

            self._adx = sum(self._dx_values) / period
            self._dx_values.clear()
        else:
            self._adx = (self._adx * (period - 1) + dx) / period

        return self._adx


@dataclass
class _IndicatorState:
    """Indicator and candle state for one symbol/timeframe pair."""

    bollinger: BollingerBands
    atr: ATR
    adx: _ADX

    latest_atr: float | None = None
    latest_adx: float | None = None

    previous_close: float | None = None
    previous_upper: float | None = None
    previous_lower: float | None = None

    last_candle_time: datetime | None = None
    last_signal_timestamp: datetime | None = None

    # Initially large so the first valid signal does not require an
    # artificial cooldown before the strategy has ever traded.
    candles_since_signal: int = 10**9


@register_strategy("bollinger_reversion")
class BollingerReversionStrategy(BaseStrategy):
    """
    Bollinger Band mean-reversion strategy, version 3.1.0.

    Long:
        - The previous close was at or below the previous lower band.
        - The current close returns above the current lower band.
        - The current close is higher than the previous close.

    Short:
        - The previous close was at or above the previous upper band.
        - The current close returns below the current upper band.
        - The current close is lower than the previous close.

    Filters:
        - Optional ADX regime filter.
        - Minimum number of candles between consecutive signals.
        - Configurable minimum reward/risk ratio.
        - Optional minimum stop distance.

    Risk management:
        - Stop distance uses ATR from the preceding completed candle.
        - Take-profit defaults to the Bollinger middle band.
        - Optional decimal price rounding is available.

    Historical-data safety:
        - BACKTEST and REPLAY modes do not warm indicators using an
          unbounded historical query during initialization. Such a query
          could return candles later than the backtest start.
        - In those modes, indicators warm up from the candles delivered
          by the simulation.
        - Live/paper modes may warm up from historical candles, provided
          the context's historical query returns data preceding the
          live stream.

    max_holding_candles is emitted as metadata only. The downstream
    execution/backtest engine must implement time-based position exits
    if that parameter is configured.
    """

    definition = StrategyDefinition(
        name="bollinger_reversion",
        version="3.1.0",
        description=(
            "Bollinger Band mean-reversion with directional candle "
            "confirmation, ADX regime filtering, signal cooldown, "
            "ATR-based stops, and mean-reversion targets."
        ),
        author="AQE",
        tags=(
            "mean-reversion",
            "bollinger",
            "atr",
            "adx",
            "candle-confirmation",
        ),
    )

    DEFAULT_PARAMETERS: dict[str, Any] = {
        "bollinger_period": 20,
        "bollinger_deviation": 2.0,
        "atr_period": 14,
        "stop_loss_atr": 1.0,
        "take_profit_atr": 1.5,
        "take_profit_mode": "middle_band",
        "minimum_reward_risk": 1.0,
        "confidence": 0.70,
        "adx_filter": True,
        "adx_period": 14,
        "max_adx": 25.0,
        "cooldown_candles": 3,
        "min_stop_distance": 0.0,
        "price_digits": None,
        "max_holding_candles": None,
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

        configured_parameters = config.parameters or {}

        unknown = set(configured_parameters) - set(self.DEFAULT_PARAMETERS)
        if unknown:
            raise ValueError(
                f"Unknown bollinger_reversion parameters: {sorted(unknown)}"
            )

        parameters = {
            **self.DEFAULT_PARAMETERS,
            **configured_parameters,
        }

        self._bollinger_period = int(parameters["bollinger_period"])
        self._bollinger_deviation = float(parameters["bollinger_deviation"])
        self._atr_period = int(parameters["atr_period"])
        self._stop_loss_atr = float(parameters["stop_loss_atr"])
        self._take_profit_atr = float(parameters["take_profit_atr"])
        self._take_profit_mode = str(parameters["take_profit_mode"]).strip().lower()
        self._minimum_reward_risk = float(parameters["minimum_reward_risk"])
        self._confidence = float(parameters["confidence"])

        self._adx_filter = bool(parameters["adx_filter"])
        self._adx_period = int(parameters["adx_period"])
        self._max_adx = float(parameters["max_adx"])
        self._cooldown_candles = int(parameters["cooldown_candles"])

        try:
            self._min_stop_distance = Decimal(str(parameters["min_stop_distance"]))
        except Exception as exc:
            raise ValueError(
                "min_stop_distance must be a valid finite number."
            ) from exc

        self._price_digits = (
            None
            if parameters["price_digits"] is None
            else int(parameters["price_digits"])
        )
        self._max_holding_candles = (
            None
            if parameters["max_holding_candles"] is None
            else int(parameters["max_holding_candles"])
        )

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

        self._validate_parameters()

    # ------------------------------------------------------------------
    # Configuration validation
    # ------------------------------------------------------------------

    def _validate_parameters(self) -> None:
        """Reject invalid strategy parameters before execution."""

        finite_parameters = {
            "bollinger_deviation": self._bollinger_deviation,
            "stop_loss_atr": self._stop_loss_atr,
            "take_profit_atr": self._take_profit_atr,
            "minimum_reward_risk": self._minimum_reward_risk,
            "confidence": self._confidence,
            "max_adx": self._max_adx,
        }

        for name, value in finite_parameters.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite.")

        if self._bollinger_period < 2:
            raise ValueError("bollinger_period must be at least 2.")
        if self._bollinger_deviation <= 0:
            raise ValueError("bollinger_deviation must be greater than 0.")
        if self._atr_period < 1:
            raise ValueError("atr_period must be at least 1.")
        if self._stop_loss_atr <= 0:
            raise ValueError("stop_loss_atr must be greater than 0.")
        if self._take_profit_atr <= 0:
            raise ValueError("take_profit_atr must be greater than 0.")
        if self._take_profit_mode not in {
            "middle_band",
            "atr",
        }:
            raise ValueError("take_profit_mode must be 'middle_band' or 'atr'.")
        if self._minimum_reward_risk <= 0:
            raise ValueError("minimum_reward_risk must be greater than 0.")
        if not 0 < self._confidence <= 1:
            raise ValueError("confidence must be greater than 0 and no greater than 1.")
        if self._adx_period < 1:
            raise ValueError("adx_period must be at least 1.")
        if not 0 < self._max_adx <= 100:
            raise ValueError("max_adx must be in the range (0, 100].")
        if self._cooldown_candles < 0:
            raise ValueError("cooldown_candles must not be negative.")
        if not self._min_stop_distance.is_finite() or self._min_stop_distance < 0:
            raise ValueError("min_stop_distance must be finite and non-negative.")
        if self._price_digits is not None and not 0 <= self._price_digits <= 10:
            raise ValueError("price_digits must be between 0 and 10.")
        if self._max_holding_candles is not None and self._max_holding_candles < 1:
            raise ValueError("max_holding_candles must be at least 1.")

    # ------------------------------------------------------------------
    # Mode and lifecycle
    # ------------------------------------------------------------------

    def _is_historical_mode(self) -> bool:
        """
        Determine whether this instance runs against a historical timeline.

        If the mode cannot be determined, prefer the safe historical
        behavior: do not query unbounded latest candles for initialization.
        """

        mode = getattr(self.config, "mode", None)

        if mode is None:
            mode = getattr(self.context, "mode", None)

        if mode is None:
            return True

        mode_value = getattr(mode, "value", mode)
        normalized = str(mode_value).strip().upper()
        normalized = normalized.rsplit(".", 1)[-1]

        return normalized in {
            "BACKTEST",
            "REPLAY",
        }

    async def on_initialize(self) -> None:
        """
        Initialize indicator state.

        BACKTEST/REPLAY mode intentionally avoids an unbounded historical
        candle query. Live/paper modes can seed indicators from historical
        candles and retain the final historical candle as the previous
        reference for the incoming live stream.
        """

        self._states.clear()

        historical_mode = self._is_historical_mode()

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                normalized_timeframe = Timeframe(str(timeframe).strip().upper())

                state = self._get_state(
                    symbol,
                    normalized_timeframe,
                )

                if historical_mode:
                    mode_value = getattr(
                        self.config.mode,
                        "value",
                        self.config.mode,
                    )
                    normalized_mode = str(mode_value).strip().upper().rsplit(".", 1)[-1]

                    if normalized_mode == "REPLAY":
                        # Replay mode warms up from its chronological feed.
                        continue

                    # BACKTEST uses a view that exposes only candles strictly
                    # before the configured test start during initialization.

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    count=max(
                        self._bollinger_period * 3,
                        self._atr_period * 3,
                        self._adx_period * 4,
                        100,
                    ),
                )

                for candle in sorted(
                    candles,
                    key=lambda item: item.datetime,
                ):
                    if (
                        state.last_candle_time is not None
                        and candle.datetime <= state.last_candle_time
                    ):
                        continue

                    bands, _, _ = self._update_indicators(
                        state,
                        candle.high,
                        candle.low,
                        candle.close,
                    )

                    if self._bands_ready(bands):
                        state.previous_close = float(candle.close)
                        state.previous_upper = float(bands.upper)
                        state.previous_lower = float(bands.lower)

                    state.last_candle_time = candle.datetime

    async def on_start(self) -> None:
        """Start the strategy."""

        return None

    async def on_stop(self) -> None:
        """Stop the strategy."""

        return None

    async def on_shutdown(self) -> None:
        """Release all per-symbol indicator state."""

        self._states.clear()

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    async def on_candle(
        self,
        candle: MarketCandle,
    ) -> TradingSignal | None:
        """Process one completed candle and optionally produce an entry."""

        symbol = candle.symbol
        timeframe = Timeframe(str(candle.timeframe).strip().upper())
        timestamp = candle.datetime

        state = self._get_state(
            symbol,
            timeframe,
        )

        # Ignore duplicate, repeated, or out-of-order candles for this
        # symbol/timeframe. The state is isolated per key.
        if state.last_candle_time is not None and timestamp <= state.last_candle_time:
            return None

        state.last_candle_time = timestamp

        # Capture the preceding ATR before incorporating this candle.
        atr_before = state.latest_atr

        bands, current_atr, current_adx = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_close = state.previous_close
        previous_upper = state.previous_upper
        previous_lower = state.previous_lower

        current_close = float(candle.close)

        # If bands are not valid yet, clear signal references rather than
        # accidentally crossing from a previous invalid indicator state.
        if not self._bands_ready(bands):
            state.previous_close = None
            state.previous_upper = None
            state.previous_lower = None
            return None

        # The current band's values become the previous reference only
        # after this candle's signal opportunity has been evaluated.
        state.previous_close = current_close
        state.previous_upper = float(bands.upper)
        state.previous_lower = float(bands.lower)

        state.candles_since_signal += 1

        if previous_close is None or previous_upper is None or previous_lower is None:
            return None

        if (
            state.last_signal_timestamp == timestamp
            or atr_before is None
            or not math.isfinite(atr_before)
            or atr_before <= 0
        ):
            return None

        # Require a valid ADX reading when the regime filter is enabled.
        if self._adx_filter:
            if current_adx is None or not math.isfinite(current_adx):
                return None

            if current_adx > self._max_adx:
                return None

        # A cooldown of N means N full candles after the last signal must
        # pass before another signal can be emitted.
        if state.candles_since_signal <= self._cooldown_candles:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None
        penetration = 0.0

        lower_band = float(bands.lower)
        upper_band = float(bands.upper)

        # Long: prior close was at/below its lower band, then price
        # returns inside the current lower band and closes higher.
        if (
            previous_close <= previous_lower
            and current_close > lower_band
            and current_close > previous_close
        ):
            direction = SignalDirection.LONG
            penetration = max(
                0.0,
                previous_lower - previous_close,
            )
            reason = (
                "Price returned above the lower Bollinger Band "
                "with bullish candle confirmation"
            )

        # Short: prior close was at/above its upper band, then price
        # returns inside the current upper band and closes lower.
        elif (
            previous_close >= previous_upper
            and current_close < upper_band
            and current_close < previous_close
        ):
            direction = SignalDirection.SHORT
            penetration = max(
                0.0,
                previous_close - previous_upper,
            )
            reason = (
                "Price returned below the upper Bollinger Band "
                "with bearish candle confirmation"
            )

        if direction is None:
            return None

        entry_price = self._quantize(Decimal(str(candle.close)))
        atr = Decimal(str(atr_before))

        stop_distance = atr * Decimal(str(self._stop_loss_atr))

        if (
            not stop_distance.is_finite()
            or stop_distance <= 0
            or stop_distance < self._min_stop_distance
        ):
            return None

        # --------------------------------------------------------------
        # Stop loss
        # --------------------------------------------------------------

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance

        # --------------------------------------------------------------
        # Take profit
        # --------------------------------------------------------------

        if self._take_profit_mode == "middle_band":
            target_price = Decimal(str(bands.middle))
        else:
            target_distance = atr * Decimal(str(self._take_profit_atr))

            if direction is SignalDirection.LONG:
                target_price = entry_price + target_distance
            else:
                target_price = entry_price - target_distance

        stop_loss = self._quantize(stop_loss)
        target_price = self._quantize(target_price)

        if not all(
            value.is_finite()
            for value in (
                entry_price,
                stop_loss,
                target_price,
            )
        ):
            return None

        # Rounding may collapse the stop or target onto the entry price.
        if direction is SignalDirection.LONG:
            if not stop_loss < entry_price < target_price:
                return None
        else:
            if not target_price < entry_price < stop_loss:
                return None

        # --------------------------------------------------------------
        # Reward / risk
        # --------------------------------------------------------------

        reward_distance = abs(target_price - entry_price)
        risk_distance = abs(entry_price - stop_loss)

        if risk_distance <= 0:
            return None

        reward_risk = reward_distance / risk_distance

        if reward_risk < Decimal(str(self._minimum_reward_risk)):
            return None

        # The confidence is a bounded heuristic score, not a statistical
        # probability of winning the trade.
        depth_ratio = min(
            1.0,
            max(
                0.0,
                penetration / atr_before,
            ),
        )

        confidence = min(
            1.0,
            self._confidence * (0.85 + 0.15 * depth_ratio),
        )

        state.last_signal_timestamp = timestamp
        state.candles_since_signal = 0

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
            take_profit=target_price,
            confidence=confidence,
            reason=reason,
            metadata={
                "middle_band": float(bands.middle),
                "upper_band": float(bands.upper),
                "lower_band": float(bands.lower),
                "standard_deviation": float(bands.standard_deviation),
                "atr": current_atr,
                "trade_atr": atr_before,
                "adx": current_adx,
                "max_adx": (self._max_adx if self._adx_filter else None),
                "penetration_atr": depth_ratio,
                "bollinger_period": self._bollinger_period,
                "bollinger_deviation": self._bollinger_deviation,
                "stop_loss_atr": self._stop_loss_atr,
                "take_profit_atr": self._take_profit_atr,
                "take_profit_mode": self._take_profit_mode,
                "minimum_reward_risk": self._minimum_reward_risk,
                "reward_risk": float(reward_risk),
                "cooldown_candles": self._cooldown_candles,
                "max_holding_candles": self._max_holding_candles,
                "direction_confirmation": True,
                "previous_close": previous_close,
                "current_close": current_close,
                "previous_upper_band": previous_upper,
                "previous_lower_band": previous_lower,
            },
        )

    # ------------------------------------------------------------------
    # State and indicator helpers
    # ------------------------------------------------------------------

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
                bollinger=BollingerBands(
                    period=self._bollinger_period,
                    deviation=self._bollinger_deviation,
                ),
                atr=ATR(self._atr_period),
                adx=_ADX(self._adx_period),
            )
            self._states[key] = state

        return state

    @staticmethod
    def _bands_ready(bands: Any) -> bool:
        """Return True only when all Bollinger values exist and are finite."""

        if bands is None:
            return False

        try:
            values = (
                float(bands.upper),
                float(bands.middle),
                float(bands.lower),
            )
        except (AttributeError, TypeError, ValueError):
            return False

        return all(math.isfinite(value) for value in values)

    def _quantize(self, value: Decimal) -> Decimal:
        """
        Round to configured decimal precision when requested.

        Decimal digits are not necessarily equivalent to a broker's tick
        size. Instrument-specific tick-size validation belongs downstream.
        """

        if self._price_digits is None:
            return value

        quantum = Decimal(1).scaleb(-self._price_digits)
        return value.quantize(quantum)

    @staticmethod
    def _update_indicators(
        state: _IndicatorState,
        high: float | Decimal,
        low: float | Decimal,
        close: float | Decimal,
    ) -> tuple[Any, float | None, float | None]:
        """
        Update Bollinger Bands, ATR, and ADX with one candle.

        on_candle captures state.latest_atr before this call, ensuring
        trade construction uses the ATR from the preceding candle.
        """

        high_value = float(high)
        low_value = float(low)
        close_value = float(close)

        if not all(
            math.isfinite(value)
            for value in (
                high_value,
                low_value,
                close_value,
            )
        ):
            raise ValueError("Candle OHLC values must be finite.")

        if high_value < low_value:
            raise ValueError("Candle high cannot be below candle low.")

        bands = state.bollinger.update(close_value)

        atr_value = state.atr.update(
            high=high_value,
            low=low_value,
            close=close_value,
        )

        if atr_value is not None:
            atr_float = float(atr_value)

            if math.isfinite(atr_float) and atr_float >= 0:
                state.latest_atr = atr_float

        adx_value = state.adx.update(
            high_value,
            low_value,
            close_value,
        )

        if adx_value is not None and math.isfinite(adx_value):
            state.latest_adx = adx_value

        return (
            bands,
            state.latest_atr,
            state.latest_adx,
        )


__all__ = [
    "BollingerReversionStrategy",
]
