"""Safe, deterministic orchestration for candle-driven paper trading."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal

from engine.broker.base import OrderSide
from engine.execution.engine import ExecutionEngine
from engine.execution.orders import Order
from engine.market.candles import Candle
from engine.risk.position_sizer import position_size
from engine.risk.validator import RiskValidator
from engine.strategy.manager import StrategyManager
from engine.strategy.signals import SignalSide


@dataclass(frozen=True)
class TradeAttempt:
    symbol: str
    strategy: str | None
    approved: bool
    reason: str
    order_id: str | None = None
    volume: Decimal = Decimal("0")


@dataclass
class AutonomousPaperTrader:
    """Run strategy signals through risk and a paper broker.

    The loop is deliberately synchronous and candle-driven so it can be called
    by a scheduler, replay service, or websocket consumer without owning an
    event loop. It never invents a stop loss: signals without one are rejected.
    """

    strategy_manager: StrategyManager
    execution: ExecutionEngine = field(default_factory=ExecutionEngine)
    risk: RiskValidator = field(default_factory=RiskValidator)
    equity: Decimal = Decimal("100000")
    risk_percent: Decimal = Decimal("1")
    tick_size: Decimal = Decimal("0.01")
    tick_value: Decimal = Decimal("1")
    volume_step: Decimal = Decimal("0.01")
    attempts: list[TradeAttempt] = field(default_factory=list)

    def on_candle(self, candle: Candle) -> list[TradeAttempt]:
        results = []
        signals = self.strategy_manager.on_candle(candle)

        for signal in signals:
            if signal.side == SignalSide.HOLD:
                continue

            if signal.stop_loss is None:
                results.append(self._reject(signal.symbol, "stop loss is required"))
                continue

            decision = self.risk.validate_trade_risk(self.risk_percent)
            if not decision.approved:
                results.append(self._reject(signal.symbol, decision.reason))
                continue

            entry = signal.entry or candle.close
            try:
                volume = position_size(
                    equity=self.equity,
                    risk_percent=self.risk_percent,
                    entry=entry,
                    stop=signal.stop_loss,
                    tick_size=self.tick_size,
                    tick_value=self.tick_value,
                    volume_step=self.volume_step,
                )
            except ValueError as exc:
                results.append(self._reject(signal.symbol, str(exc)))
                continue

            if volume <= 0:
                results.append(self._reject(signal.symbol, "calculated volume is zero"))
                continue

            order = Order(
                symbol=signal.symbol,
                side=OrderSide(signal.side.value),
                volume=volume,
                price=entry,
            ).with_id()
            fill = self.execution.execute(order)
            result = TradeAttempt(
                symbol=signal.symbol,
                strategy=None,
                approved=True,
                reason="filled",
                order_id=fill.order_id,
                volume=fill.volume,
            )
            self.attempts.append(result)
            results.append(result)

        return results

    async def run_feed(
        self,
        feed: AsyncIterator[Candle],
        max_candles: int | None = None,
    ) -> list[TradeAttempt]:
        processed = 0
        async for candle in feed:
            self.on_candle(candle)
            processed += 1
            if max_candles is not None and processed >= max_candles:
                break
        return self.attempts

    def _reject(self, symbol: str, reason: str) -> TradeAttempt:
        result = TradeAttempt(
            symbol=symbol,
            strategy=None,
            approved=False,
            reason=reason,
        )
        self.attempts.append(result)
        return result