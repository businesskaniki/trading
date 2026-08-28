"""
EMA trend-following strategy for AQE.

The strategy identifies directional trends using fast and slow
exponential moving averages, price confirmation, EMA slope, and
minimum EMA separation.

This module:
    - consumes StrategyContext
    - analyzes normalized market data
    - generates Signal objects

This module does NOT:
    - connect to MT5
    - place orders
    - calculate account-level risk
    - determine position size
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from strategies.core.base import BaseStrategy
from strategies.core.context import StrategyContext
from strategies.core.enums import (
    Direction,
    OrderType,
    SignalType,
    StrategyCategory,
    Timeframe,
)
from strategies.core.signal import Signal


class EMATrendStrategy(BaseStrategy):
    """
    EMA trend-following strategy.

    Default configuration:

        Fast EMA: 9
        Slow EMA: 21
        ATR: 14
        ATR multiplier: 1.5
        Risk/reward: 2.0
        Minimum EMA separation: 0.0001

    Entry requires:

        BUY:
            - fast EMA crosses above slow EMA
            - price is above fast EMA
            - fast EMA is rising
            - EMA separation meets minimum threshold

        SELL:
            - fast EMA crosses below slow EMA
            - price is below fast EMA
            - fast EMA is falling
            - EMA separation meets minimum threshold

    Stop-loss and take-profit are derived from ATR.

    The resulting Signal is passed to the Risk Engine before execution.
    """

    # ------------------------------------------------------------------
    # Strategy identity
    # ------------------------------------------------------------------

    strategy_id = "ema_trend"

    name = "EMA Trend Following"

    category = StrategyCategory.TREND

    description = (
        "Trend-following strategy using fast and slow EMA alignment "
        "with price confirmation, EMA slope, and ATR-based risk levels."
    )

    timeframe = Timeframe.M15

    minimum_candles = 50

    # ------------------------------------------------------------------
    # Default parameters
    # ------------------------------------------------------------------

    DEFAULT_FAST_PERIOD = 9
    DEFAULT_SLOW_PERIOD = 21
    DEFAULT_ATR_PERIOD = 14

    DEFAULT_ATR_MULTIPLIER = Decimal("1.5")
    DEFAULT_RISK_REWARD = Decimal("2.0")

    DEFAULT_MIN_EMA_SEPARATION = Decimal("0.0001")

    # ------------------------------------------------------------------
    # Main strategy logic
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Analyze the current market and generate a trading signal.

        Returns:
            Signal:
                When a valid EMA trend setup exists.

            None:
                When no valid setup exists.
        """

        candles = list(context.market_data.candles)

        # --------------------------------------------------------------
        # Strategy parameters
        # --------------------------------------------------------------

        fast_period = self._get_int_parameter(
            context,
            "fast_period",
            self.DEFAULT_FAST_PERIOD,
        )

        slow_period = self._get_int_parameter(
            context,
            "slow_period",
            self.DEFAULT_SLOW_PERIOD,
        )

        atr_period = self._get_int_parameter(
            context,
            "atr_period",
            self.DEFAULT_ATR_PERIOD,
        )

        atr_multiplier = self._get_decimal_parameter(
            context,
            "atr_multiplier",
            self.DEFAULT_ATR_MULTIPLIER,
        )

        risk_reward = self._get_decimal_parameter(
            context,
            "risk_reward",
            self.DEFAULT_RISK_REWARD,
        )

        min_ema_separation = self._get_decimal_parameter(
            context,
            "min_ema_separation",
            self.DEFAULT_MIN_EMA_SEPARATION,
        )

        # --------------------------------------------------------------
        # Validate parameters
        # --------------------------------------------------------------

        self._validate_parameters(
            fast_period=fast_period,
            slow_period=slow_period,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            risk_reward=risk_reward,
            min_ema_separation=min_ema_separation,
        )

        # --------------------------------------------------------------
        # Ensure sufficient historical data
        # --------------------------------------------------------------

        required_candles = max(
            slow_period,
            atr_period,
        ) + 2

        if len(candles) < required_candles:
            return None

        # --------------------------------------------------------------
        # Price series
        # --------------------------------------------------------------

        closes = [
            candle.close
            for candle in candles
        ]

        # --------------------------------------------------------------
        # Indicators
        # --------------------------------------------------------------

        fast_ema = self._ema(
            closes,
            fast_period,
        )

        slow_ema = self._ema(
            closes,
            slow_period,
        )

        atr = self._atr(
            candles,
            atr_period,
        )

        if not fast_ema or not slow_ema or atr is None:
            return None

        # --------------------------------------------------------------
        # Current market state
        # --------------------------------------------------------------

        latest_close = candles[-1].close

        previous_close = candles[-2].close

        latest_fast = fast_ema[-1]
        previous_fast = fast_ema[-2]

        latest_slow = slow_ema[-1]
        previous_slow = slow_ema[-2]

        # --------------------------------------------------------------
        # EMA structure
        # --------------------------------------------------------------

        ema_separation = abs(
            latest_fast - latest_slow
        )

        fast_ema_rising = (
            latest_fast > previous_fast
        )

        fast_ema_falling = (
            latest_fast < previous_fast
        )

        # --------------------------------------------------------------
        # BUY setup
        # --------------------------------------------------------------

        bullish_cross = (
            previous_fast <= previous_slow
            and latest_fast > latest_slow
        )

        bullish_alignment = (
            latest_fast > latest_slow
            and latest_close > latest_fast
        )

        bullish_trend = (
            fast_ema_rising
            and ema_separation >= min_ema_separation
        )

        bullish_momentum = (
            latest_close > previous_close
        )

        if (
            bullish_cross
            and bullish_alignment
            and bullish_trend
            and bullish_momentum
        ):
            return self._build_signal(
                context=context,
                direction=Direction.BUY,
                entry_price=latest_close,
                atr=atr,
                atr_multiplier=atr_multiplier,
                risk_reward=risk_reward,
                ema_separation=ema_separation,
                reason=(
                    "Bullish EMA crossover with price above "
                    "the fast EMA, rising EMA slope, sufficient "
                    "EMA separation, and bullish price momentum."
                ),
            )

        # --------------------------------------------------------------
        # SELL setup
        # --------------------------------------------------------------

        bearish_cross = (
            previous_fast >= previous_slow
            and latest_fast < latest_slow
        )

        bearish_alignment = (
            latest_fast < latest_slow
            and latest_close < latest_fast
        )

        bearish_trend = (
            fast_ema_falling
            and ema_separation >= min_ema_separation
        )

        bearish_momentum = (
            latest_close < previous_close
        )

        if (
            bearish_cross
            and bearish_alignment
            and bearish_trend
            and bearish_momentum
        ):
            return self._build_signal(
                context=context,
                direction=Direction.SELL,
                entry_price=latest_close,
                atr=atr,
                atr_multiplier=atr_multiplier,
                risk_reward=risk_reward,
                ema_separation=ema_separation,
                reason=(
                    "Bearish EMA crossover with price below "
                    "the fast EMA, falling EMA slope, sufficient "
                    "EMA separation, and bearish price momentum."
                ),
            )

        return None

    # ------------------------------------------------------------------
    # Signal construction
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        *,
        context: StrategyContext,
        direction: Direction,
        entry_price: Decimal,
        atr: Decimal,
        atr_multiplier: Decimal,
        risk_reward: Decimal,
        ema_separation: Decimal,
        reason: str,
    ) -> Signal:
        """
        Build a standardized AQE Signal.

        Position sizing and risk approval are intentionally excluded.
        """

        risk_distance = (
            atr * atr_multiplier
        )

        if direction == Direction.BUY:

            stop_loss = (
                entry_price - risk_distance
            )

            take_profit = (
                entry_price
                + (
                    risk_distance
                    * risk_reward
                )
            )

        else:

            stop_loss = (
                entry_price + risk_distance
            )

            take_profit = (
                entry_price
                - (
                    risk_distance
                    * risk_reward
                )
            )

        return Signal(
            signal_id=self._generate_signal_id(
                context=context,
                direction=direction,
            ),
            strategy_id=self.strategy_id,
            symbol=context.symbol,
            timeframe=context.timeframe,
            signal_type=SignalType.ENTRY,
            direction=direction,
            order_type=OrderType.MARKET,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=self._calculate_confidence(
                context=context,
                direction=direction,
                ema_separation=ema_separation,
            ),
            created_at=datetime.now(timezone.utc),
            reason=reason,
            metadata={
                "fast_period": self._get_int_parameter(
                    context,
                    "fast_period",
                    self.DEFAULT_FAST_PERIOD,
                ),
                "slow_period": self._get_int_parameter(
                    context,
                    "slow_period",
                    self.DEFAULT_SLOW_PERIOD,
                ),
                "atr_period": self._get_int_parameter(
                    context,
                    "atr_period",
                    self.DEFAULT_ATR_PERIOD,
                ),
                "atr": str(atr),
                "atr_multiplier": str(
                    atr_multiplier
                ),
                "risk_reward": str(
                    risk_reward
                ),
                "ema_separation": str(
                    ema_separation
                ),
            },
        )

    # ------------------------------------------------------------------
    # EMA calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(
        values: Sequence[Decimal],
        period: int,
    ) -> list[Decimal]:
        """
        Calculate an exponential moving average.

        The initial EMA value is calculated using an SMA.

        Subsequent values use:

            EMA = (Price - Previous EMA) × Multiplier
                  + Previous EMA

        Multiplier:

            2 / (period + 1)
        """

        if len(values) < period:
            return []

        multiplier = (
            Decimal("2")
            / Decimal(period + 1)
        )

        initial_sum = sum(
            values[:period],
            Decimal("0"),
        )

        initial_ema = (
            initial_sum
            / Decimal(period)
        )

        ema_values: list[Decimal] = [
            initial_ema
        ]

        for value in values[period:]:

            previous_ema = ema_values[-1]

            current_ema = (
                (
                    value - previous_ema
                )
                * multiplier
            ) + previous_ema

            ema_values.append(
                current_ema
            )

        # Keep EMA indexes aligned with candles.
        padding = [
            values[0]
        ] * (period - 1)

        return padding + ema_values

    # ------------------------------------------------------------------
    # ATR calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _atr(
        candles,
        period: int,
    ) -> Decimal | None:
        """
        Calculate Average True Range using Wilder smoothing.
        """

        if len(candles) < period + 1:
            return None

        true_ranges: list[Decimal] = []

        for index in range(1, len(candles)):

            current = candles[index]

            previous = candles[index - 1]

            high_low = (
                current.high
                - current.low
            )

            high_previous_close = abs(
                current.high
                - previous.close
            )

            low_previous_close = abs(
                current.low
                - previous.close
            )

            true_range = max(
                high_low,
                high_previous_close,
                low_previous_close,
            )

            true_ranges.append(
                true_range
            )

        if len(true_ranges) < period:
            return None

        atr = (
            sum(
                true_ranges[:period],
                Decimal("0"),
            )
            / Decimal(period)
        )

        for true_range in true_ranges[period:]:

            atr = (
                (
                    atr
                    * Decimal(period - 1)
                )
                + true_range
            ) / Decimal(period)

        return atr

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_confidence(
        *,
        context: StrategyContext,
        direction: Direction,
        ema_separation: Decimal,
    ) -> Decimal:
        """
        Calculate deterministic strategy confidence.

        This is a setup-strength score, NOT a probability of winning.

        A future model-based confidence system can replace this method.
        """

        candles = list(
            context.market_data.candles
        )

        if len(candles) < 2:
            return Decimal("0.50")

        latest = candles[-1]

        previous = candles[-2]

        confidence = Decimal("0.60")

        # Price momentum confirmation.
        if direction == Direction.BUY:

            if latest.close > previous.close:
                confidence += Decimal("0.10")

        else:

            if latest.close < previous.close:
                confidence += Decimal("0.10")

        # Additional confidence for meaningful EMA separation.
        if ema_separation >= Decimal("0.0002"):
            confidence += Decimal("0.10")

        return min(
            confidence,
            Decimal("0.95"),
        )

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_int_parameter(
        context: StrategyContext,
        name: str,
        default: int,
    ) -> int:
        """
        Retrieve and convert an integer strategy parameter.
        """

        value = context.strategy.parameters.get(
            name,
            default,
        )

        try:
            return int(value)

        except (TypeError, ValueError) as exc:

            raise ValueError(
                f"Strategy parameter '{name}' "
                "must be an integer"
            ) from exc

    @staticmethod
    def _get_decimal_parameter(
        context: StrategyContext,
        name: str,
        default: Decimal,
    ) -> Decimal:
        """
        Retrieve and convert a Decimal strategy parameter.
        """

        value = context.strategy.parameters.get(
            name,
            default,
        )

        try:
            return Decimal(str(value))

        except (TypeError, ValueError) as exc:

            raise ValueError(
                f"Strategy parameter '{name}' "
                "must be numeric"
            ) from exc

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_parameters(
        *,
        fast_period: int,
        slow_period: int,
        atr_period: int,
        atr_multiplier: Decimal,
        risk_reward: Decimal,
        min_ema_separation: Decimal,
    ) -> None:
        """
        Validate strategy configuration.
        """

        if fast_period <= 0:
            raise ValueError(
                "fast_period must be greater than zero"
            )

        if slow_period <= fast_period:
            raise ValueError(
                "slow_period must be greater than "
                "fast_period"
            )

        if atr_period <= 0:
            raise ValueError(
                "atr_period must be greater than zero"
            )

        if atr_multiplier <= 0:
            raise ValueError(
                "atr_multiplier must be greater than zero"
            )

        if risk_reward <= 0:
            raise ValueError(
                "risk_reward must be greater than zero"
            )

        if min_ema_separation < 0:
            raise ValueError(
                "min_ema_separation cannot be negative"
            )

    # ------------------------------------------------------------------
    # Signal ID
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_signal_id(
        *,
        context: StrategyContext,
        direction: Direction,
    ) -> str:
        """
        Generate a unique signal identifier.
        """

        timestamp = (
            context.timestamp.isoformat()
        )

        return (
            f"{context.symbol}_"
            f"{context.timeframe.value}_"
            f"ema_trend_"
            f"{direction.value}_"
            f"{timestamp}"
        )