"""RSI mean-reversion strategy with ATR-based risk levels."""

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
from strategies.indicators import ATR, RSI


@dataclass
class _IndicatorState:
    """Indicator state for one symbol/timeframe pair."""

    rsi: RSI
    atr: ATR

    previous_rsi: float | None = None
    previous_atr: float | None = None

    last_signal_timestamp: datetime | None = None


@register_strategy("rsi_reversal")
class RSIReversalStrategy(BaseStrategy):
    """
    RSI mean-reversion strategy.

    Long:
        RSI crosses back above the oversold level.

    Short:
        RSI crosses back below the overbought level.

    Risk management:
        Stop-loss and take-profit are ATR based.

        The ATR from the previous completed candle is used when
        constructing the trade so that the signal candle does not
        determine its own risk distance.
    """

    definition = StrategyDefinition(
        name="rsi_reversal",
        version="2.0.0",
        description=(
            "RSI mean-reversion strategy with "
            "ATR-based stop-loss and take-profit."
        ),
        author="AQE",
        tags=(
            "mean-reversion",
            "rsi",
            "atr",
            "reversal",
        ),
    )

    DEFAULT_PARAMETERS = {
        "rsi_period": 14,
        "atr_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,

        # Mean-reversion trades should not normally require
        # a very wide trend-style stop.
        "stop_loss_atr": 1.0,

        # 1.5 ATR target against a 1.0 ATR stop gives 1.5R.
        "take_profit_atr": 1.5,

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

        self._rsi_period = int(
            parameters["rsi_period"]
        )

        self._atr_period = int(
            parameters["atr_period"]
        )

        self._oversold = float(
            parameters["oversold"]
        )

        self._overbought = float(
            parameters["overbought"]
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

        self._states: dict[
            tuple[str, Timeframe],
            _IndicatorState,
        ] = {}

    async def on_initialize(self) -> None:
        """Initialize indicator state and warm up from historical candles."""

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
                        self._rsi_period * 3,
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
        """Release strategy resources."""

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

        # Preserve the ATR from the previous completed candle.
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

        if current_rsi < 0.0 or current_rsi > 100.0:
            return None

        timestamp = candle.datetime

        if state.last_signal_timestamp == timestamp:
            return None

        direction: SignalDirection | None = None
        reason: str | None = None

        # --------------------------------------------------------------
        # Long mean-reversion setup
        # --------------------------------------------------------------

        if (
            previous_rsi <= self._oversold
            and current_rsi > self._oversold
        ):
            direction = SignalDirection.LONG
            reason = (
                f"RSI recovered above oversold level "
                f"({self._oversold:.2f})"
            )

        # --------------------------------------------------------------
        # Short mean-reversion setup
        # --------------------------------------------------------------

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

        entry_price = Decimal(
            str(candle.close)
        )

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
                "rsi": current_rsi,
                "previous_rsi": previous_rsi,
                "atr": current_atr,
                "trade_atr": previous_atr,
                "oversold": self._oversold,
                "overbought": self._overbought,
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
                rsi=RSI(
                    self._rsi_period
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
    ) -> tuple[float, float]:
        """Update RSI and ATR from one candle."""

        rsi_value = state.rsi.update(
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
            rsi_value,
            atr_value,
        )


__all__ = [
    "RSIReversalStrategy",
]