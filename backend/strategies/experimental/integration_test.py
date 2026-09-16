"""Simple strategy used to validate the AQE Strategy Runtime pipeline."""

from __future__ import annotations

from app.events.market import MarketCandleEvent

from ..core import (
    BaseStrategy,
    OrderType,
    SignalDirection,
    SignalType,
    StrategyDefinition,
    TradingSignal,
    Timeframe,
    register_strategy,
)


@register_strategy("integration_test")
class IntegrationTestStrategy(BaseStrategy):
    """
    Minimal candle-based strategy used to validate Strategy Engine wiring.

    Behaviour:

        Bullish candle:
            close > open
            -> LONG entry signal

        Bearish candle:
            close < open
            -> SHORT entry signal

        Neutral candle:
            close == open
            -> no signal

    This strategy intentionally contains no sophisticated trading logic.
    Its purpose is to verify:

        MarketCandleEvent
            -> Dispatcher
            -> StrategyInstance
            -> Strategy
            -> TradingSignal
            -> EventBus

    It does not communicate with:
        - Redis
        - MT5
        - PostgreSQL
        - Risk Engine
        - Execution Engine
    """

    definition = StrategyDefinition(
        name="integration_test",
        version="1.0.0",
        description=(
            "Minimal candle-based strategy used to validate "
            "the AQE Strategy Engine runtime."
        ),
        author="AQE",
        tags=[
            "experimental",
            "integration",
            "test",
        ],
    )

    async def on_candle(
        self,
        event: MarketCandleEvent,
    ) -> TradingSignal | None:
        """
        Process a completed candle and optionally generate a signal.

        A bullish candle generates a LONG signal.

        A bearish candle generates a SHORT signal.

        A doji generates no signal.
        """

        candle = event.candle

        if candle.close == candle.open:
            return None

        entry_price = candle.close

        stop_distance = self._stop_distance(entry_price)
        target_distance = self._target_distance(entry_price)

        if candle.close > candle.open:
            return TradingSignal(
                strategy_id=self.strategy_id,
                strategy_name=self.strategy_name,
                symbol=candle.symbol,
                timeframe=Timeframe(candle.timeframe),
                signal_type=SignalType.ENTRY,
                direction=SignalDirection.LONG,
                order_type=OrderType.MARKET,
                timestamp=candle.datetime,
                entry_price=entry_price,
                stop_loss=entry_price - stop_distance,
                take_profit=entry_price + target_distance,
                confidence=self._confidence(),
                reason=(
                    "Integration test: bullish candle generated " "a LONG entry signal."
                ),
                metadata={
                    "strategy_mode": self.mode.value,
                    "candle_open": candle.open,
                    "candle_high": candle.high,
                    "candle_low": candle.low,
                    "candle_close": candle.close,
                },
            )

        return TradingSignal(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            symbol=candle.symbol,
            timeframe=Timeframe(candle.timeframe),
            signal_type=SignalType.ENTRY,
            direction=SignalDirection.SHORT,
            order_type=OrderType.MARKET,
            timestamp=candle.datetime,
            entry_price=entry_price,
            stop_loss=entry_price + stop_distance,
            take_profit=entry_price - target_distance,
            confidence=self._confidence(),
            reason=(
                "Integration test: bearish candle generated " "a SHORT entry signal."
            ),
            metadata={
                "strategy_mode": self.mode.value,
                "candle_open": candle.open,
                "candle_high": candle.high,
                "candle_low": candle.low,
                "candle_close": candle.close,
            },
        )

    def _stop_distance(self, price: float) -> float:
        """
        Calculate the stop-loss distance.

        The percentage can be overridden through strategy parameters.
        """

        percentage = float(
            self.context.parameter(
                "stop_loss_percent",
                0.01,
            )
        )

        if percentage <= 0:
            percentage = 0.01

        return price * percentage

    def _target_distance(self, price: float) -> float:
        """
        Calculate the take-profit distance.

        The percentage can be overridden through strategy parameters.
        """

        percentage = float(
            self.context.parameter(
                "take_profit_percent",
                0.02,
            )
        )

        if percentage <= 0:
            percentage = 0.02

        return price * percentage

    def _confidence(self) -> float:
        """
        Return the configured signal confidence.

        The integration strategy defaults to full confidence because
        confidence is not the purpose being tested here.
        """

        confidence = float(
            self.context.parameter(
                "confidence",
                1.0,
            )
        )

        return max(0.0, min(1.0, confidence))
