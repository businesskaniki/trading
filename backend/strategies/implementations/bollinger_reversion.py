"""Bollinger Band mean-reversion strategy with ATR-based risk management."""

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
from strategies.indicators import ATR, BollingerBands


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    bollinger: BollingerBands
    atr: ATR

    previous_close: float | None = None
    previous_upper: float | None = None
    previous_lower: float | None = None
    previous_atr: float | None = None

    last_signal_timestamp: datetime | None = None


@register_strategy("bollinger_reversion")
class BollingerReversionStrategy(BaseStrategy):
    """
    Bollinger Band mean-reversion strategy.

    Long:
        Price was below the lower Bollinger Band and
        closes back inside the bands.

    Short:
        Price was above the upper Bollinger Band and
        closes back inside the bands.

    Risk management:
        Stop-loss is ATR based.

        Take-profit defaults to the Bollinger middle band,
        which is the natural mean-reversion target.

        A signal is only emitted when the projected target
        provides at least the configured minimum reward/risk.
    """

    definition = StrategyDefinition(
        name="bollinger_reversion",
        version="2.0.0",
        description=(
            "Bollinger Band mean-reversion strategy with "
            "ATR-based stop-loss and mean-reversion take-profit."
        ),
        author="AQE",
        tags=(
            "mean-reversion",
            "bollinger",
            "atr",
        ),
    )

    DEFAULT_PARAMETERS = {
        "bollinger_period": 20,
        "bollinger_deviation": 2.0,
        "atr_period": 14,

        # More appropriate for a mean-reversion setup than 1.5 ATR.
        "stop_loss_atr": 1.0,

        # Supported for backwards compatibility when
        # take_profit_mode == "atr".
        "take_profit_atr": 1.5,

        # "middle_band" is the default and intended mode.
        "take_profit_mode": "middle_band",

        # Strategy-level quality filter.
        "minimum_reward_risk": 1.0,

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

        self._bollinger_period = int(
            parameters["bollinger_period"]
        )

        self._bollinger_deviation = float(
            parameters["bollinger_deviation"]
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

        self._take_profit_mode = str(
            parameters["take_profit_mode"]
        ).strip().lower()

        self._minimum_reward_risk = float(
            parameters["minimum_reward_risk"]
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
                normalized_timeframe = Timeframe(timeframe)

                state = self._get_state(
                    symbol,
                    normalized_timeframe,
                )

                candles = await self.context.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    count=max(
                        self._bollinger_period * 3,
                        self._atr_period * 3,
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
        """Process a completed candle."""

        symbol = candle.symbol

        timeframe = Timeframe(
            str(candle.timeframe).strip().upper()
        )

        state = self._get_state(
            symbol,
            timeframe,
        )

        # IMPORTANT:
        # Use the ATR from the previous completed candle when
        # calculating the trade's stop distance. This prevents
        # the signal candle itself from widening its own risk.
        previous_atr = state.previous_atr

        bands, current_atr = self._update_indicators(
            state,
            candle.high,
            candle.low,
            candle.close,
        )

        previous_close = state.previous_close
        previous_upper = state.previous_upper
        previous_lower = state.previous_lower

        state.previous_close = float(candle.close)
        state.previous_upper = float(bands.upper)
        state.previous_lower = float(bands.lower)

        if (
            previous_close is None
            or previous_upper is None
            or previous_lower is None
        ):
            return None

        if previous_atr is None or previous_atr <= 0:
            return None

        timestamp = candle.datetime

        if state.last_signal_timestamp == timestamp:
            return None

        current_close = float(candle.close)

        direction: SignalDirection | None = None
        reason: str | None = None

        # --------------------------------------------------------------
        # Long mean-reversion setup
        # --------------------------------------------------------------

        if (
            previous_close <= previous_lower
            and current_close > bands.lower
        ):
            direction = SignalDirection.LONG
            reason = (
                "Price reverted above the lower Bollinger Band"
            )

        # --------------------------------------------------------------
        # Short mean-reversion setup
        # --------------------------------------------------------------

        elif (
            previous_close >= previous_upper
            and current_close < bands.upper
        ):
            direction = SignalDirection.SHORT
            reason = (
                "Price reverted below the upper Bollinger Band"
            )

        if direction is None:
            return None

        entry_price = Decimal(str(candle.close))

        atr = Decimal(str(previous_atr))

        stop_distance = (
            atr * Decimal(str(self._stop_loss_atr))
        )

        if stop_distance <= 0:
            return None

        # --------------------------------------------------------------
        # Stop-loss
        # --------------------------------------------------------------

        if direction is SignalDirection.LONG:
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance

        # --------------------------------------------------------------
        # Take-profit
        # --------------------------------------------------------------

        if self._take_profit_mode == "middle_band":
            target_price = Decimal(
                str(bands.middle)
            )

        elif self._take_profit_mode == "atr":
            target_distance = (
                atr
                * Decimal(str(self._take_profit_atr))
            )

            if direction is SignalDirection.LONG:
                target_price = (
                    entry_price + target_distance
                )
            else:
                target_price = (
                    entry_price - target_distance
                )

        else:
            # Invalid configuration should not silently
            # create an invalid order.
            return None

        # --------------------------------------------------------------
        # Validate target direction
        # --------------------------------------------------------------

        if direction is SignalDirection.LONG:
            if target_price <= entry_price:
                return None
        else:
            if target_price >= entry_price:
                return None

        # --------------------------------------------------------------
        # Reward / risk filter
        # --------------------------------------------------------------

        reward_distance = abs(
            target_price - entry_price
        )

        risk_distance = abs(
            entry_price - stop_loss
        )

        if risk_distance <= 0:
            return None

        reward_risk = (
            reward_distance / risk_distance
        )

        if (
            reward_risk
            < Decimal(
                str(self._minimum_reward_risk)
            )
        ):
            return None

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
            take_profit=target_price,
            confidence=self._confidence,
            reason=reason,
            metadata={
                "middle_band": bands.middle,
                "upper_band": bands.upper,
                "lower_band": bands.lower,
                "standard_deviation": (
                    bands.standard_deviation
                ),
                "atr": current_atr,
                "trade_atr": previous_atr,
                "bollinger_period": (
                    self._bollinger_period
                ),
                "bollinger_deviation": (
                    self._bollinger_deviation
                ),
                "stop_loss_atr": (
                    self._stop_loss_atr
                ),
                "take_profit_atr": (
                    self._take_profit_atr
                ),
                "take_profit_mode": (
                    self._take_profit_mode
                ),
                "minimum_reward_risk": (
                    self._minimum_reward_risk
                ),
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
        """
        Update Bollinger Bands and ATR from one candle.

        The resulting ATR is stored as previous_atr so the next
        candle can use it for trade construction.
        """

        bands = state.bollinger.update(
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
            bands,
            atr_value,
        )


__all__ = [
    "BollingerReversionStrategy",
]