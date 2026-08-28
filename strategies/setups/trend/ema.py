"""
EMA Trend Following Strategy.

AQE strategy responsible only for identifying EMA crossover setups
and producing standardized trading signals.

Execution, risk management, position sizing, and MT5 communication
are handled by other layers of the system.
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
    EMA crossover trend-following strategy.

    BUY:
        Fast EMA crosses above slow EMA
        AND price closes above fast EMA.

    SELL:
        Fast EMA crosses below slow EMA
        AND price closes below fast EMA.

    Risk levels:
        Stop loss = ATR × multiplier
        Take profit = risk distance × reward ratio
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    strategy_id = "ema_trend"

    name = "EMA Trend Following"

    category = StrategyCategory.TREND

    description = (
        "EMA crossover trend-following strategy with "
        "ATR-based stop loss and take profit."
    )

    timeframe = Timeframe.M15

    minimum_candles = 50

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    DEFAULT_FAST_PERIOD = 9

    DEFAULT_SLOW_PERIOD = 21

    DEFAULT_ATR_PERIOD = 14

    DEFAULT_ATR_MULTIPLIER = Decimal("1.5")

    DEFAULT_RISK_REWARD = Decimal("2.0")

    # ------------------------------------------------------------------
    # Strategy evaluation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Evaluate the current market state.

        Returns:
            Signal when a valid EMA crossover occurs.
            None otherwise.
        """

        candles = list(
            context.market_data.candles
        )

        # --------------------------------------------------------------
        # Parameters
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

        # --------------------------------------------------------------
        # Validate
        # --------------------------------------------------------------

        self._validate_parameters(
            fast_period=fast_period,
            slow_period=slow_period,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            risk_reward=risk_reward,
        )

        # --------------------------------------------------------------
        # Candle requirement
        # --------------------------------------------------------------

        required_candles = (
            max(
                slow_period,
                atr_period,
            )
            + 2
        )

        if len(candles) < required_candles:
            return None

        # --------------------------------------------------------------
        # Close prices
        # --------------------------------------------------------------

        closes = [
            candle.close
            for candle in candles
        ]

        # --------------------------------------------------------------
        # EMA
        # --------------------------------------------------------------

        fast_ema = self._ema(
            closes,
            fast_period,
        )

        slow_ema = self._ema(
            closes,
            slow_period,
        )

        if not fast_ema or not slow_ema:
            return None

        # --------------------------------------------------------------
        # ATR
        # --------------------------------------------------------------

        atr = self._atr(
            candles,
            atr_period,
        )

        if atr is None:
            return None

        # --------------------------------------------------------------
        # Current values
        # --------------------------------------------------------------

        latest_close = candles[-1].close

        previous_fast = fast_ema[-2]

        latest_fast = fast_ema[-1]

        previous_slow = slow_ema[-2]

        latest_slow = slow_ema[-1]

        # --------------------------------------------------------------
        # Bullish crossover
        # --------------------------------------------------------------

        bullish_cross = (
            previous_fast <= previous_slow
            and latest_fast > latest_slow
        )

        bullish_price_confirmation = (
            latest_close > latest_fast
        )

        if (
            bullish_cross
            and bullish_price_confirmation
        ):
            return self._build_signal(
                context=context,
                direction=Direction.BUY,
                entry_price=latest_close,
                atr=atr,
                atr_multiplier=atr_multiplier,
                risk_reward=risk_reward,
                reason=(
                    "Fast EMA crossed above slow EMA "
                    "with price above the fast EMA."
                ),
            )

        # --------------------------------------------------------------
        # Bearish crossover
        # --------------------------------------------------------------

        bearish_cross = (
            previous_fast >= previous_slow
            and latest_fast < latest_slow
        )

        bearish_price_confirmation = (
            latest_close < latest_fast
        )

        if (
            bearish_cross
            and bearish_price_confirmation
        ):
            return self._build_signal(
                context=context,
                direction=Direction.SELL,
                entry_price=latest_close,
                atr=atr,
                atr_multiplier=atr_multiplier,
                risk_reward=risk_reward,
                reason=(
                    "Fast EMA crossed below slow EMA "
                    "with price below the fast EMA."
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
        reason: str,
    ) -> Signal:
        """
        Construct the standardized AQE signal.
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
            ),
            created_at=datetime.now(
                timezone.utc
            ),
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
            },
        )

    # ------------------------------------------------------------------
    # EMA
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(
        values: Sequence[Decimal],
        period: int,
    ) -> list[Decimal]:
        """
        Calculate EMA using an SMA seed.
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

        ema_values = [
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

        padding = [
            values[0]
        ] * (period - 1)

        return (
            padding
            + ema_values
        )

    # ------------------------------------------------------------------
    # ATR
    # ------------------------------------------------------------------

    @staticmethod
    def _atr(
        candles,
        period: int,
    ) -> Decimal | None:
        """
        Calculate ATR using Wilder smoothing.
        """

        if len(candles) < period + 1:
            return None

        true_ranges: list[Decimal] = []

        for index in range(
            1,
            len(candles),
        ):
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
    ) -> Decimal:
        """
        Return a deterministic setup confidence score.

        This is NOT a probability of winning.
        """

        candles = list(
            context.market_data.candles
        )

        if len(candles) < 2:
            return Decimal("0.50")

        latest = candles[-1]

        previous = candles[-2]

        if direction == Direction.BUY:

            if latest.close > previous.close:
                return Decimal("0.75")

            return Decimal("0.60")

        if latest.close < previous.close:
            return Decimal("0.75")

        return Decimal("0.60")

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
        Retrieve an integer strategy parameter.
        """

        value = context.strategy.parameters.get(
            name,
            default,
        )

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ) as exc:

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
        Retrieve a Decimal strategy parameter.
        """

        value = context.strategy.parameters.get(
            name,
            default,
        )

        try:
            return Decimal(
                str(value)
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"Strategy parameter '{name}' "
                "must be numeric"
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_parameters(
        *,
        fast_period: int,
        slow_period: int,
        atr_period: int,
        atr_multiplier: Decimal,
        risk_reward: Decimal,
    ) -> None:
        """
        Validate strategy parameters.
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
        Generate the signal identifier.
        """

        return (
            f"{context.symbol}_"
            f"{context.timeframe.value}_"
            f"ema_trend_"
            f"{direction.value}_"
            f"{context.timestamp.isoformat()}"
        )