
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import traceback

from app.events.market import MarketCandleEvent
from app.market_data.models import MarketCandle
from app.schemas.execution import (
    ExecutionOrder,
    OrderSide as ExecOrderSide,
    OrderType as ExecOrderType,
)
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.models import (
    AccountRiskSnapshot,
    MarketPricing,
    PositionRiskSnapshot,
    RiskContext,
    RiskDecision,
    SymbolRiskConstraints,
)
from strategies.core.enums import SignalDirection
from strategies.core.signal import TradingSignal
from strategies.runtime.manager import StrategyManager

from .engine import BacktestEngine, BacktestExecutionRecord
from .market import BacktestCandle, BacktestMarketEvent
from .market_data_view import BacktestMarketDataView
from .position import BacktestPositionSide


class BacktestOrchestrationError(Exception):
    """Base exception for backtest orchestration failures."""


@dataclass(slots=True)
class BacktestRiskConfiguration:
    """
    Risk configuration used by the real AQE RiskEngine.

    The backtest orchestration layer does not implement risk rules.
    It only builds the RiskContext consumed by RiskEngine.
    """

    config: RiskConfig


@dataclass(slots=True)
class BacktestOrchestrationResult:
    """
    Results produced by the strategy -> risk -> execution pipeline.
    """

    signals_received: int = 0

    risk_evaluations: int = 0

    approved_decisions: int = 0

    rejected_decisions: int = 0

    execution_orders: int = 0

    executions: list[BacktestExecutionRecord] = field(
        default_factory=list,
    )

    risk_decisions: list[RiskDecision] = field(
        default_factory=list,
    )

    errors: list[str] = field(
        default_factory=list,
    )


class BacktestOrchestrator:
    """
    Integrates the existing AQE Strategy Runtime, Risk Engine,
    and Backtest Execution Engine.

    Responsibilities:

        Historical Market Data
                |
                v
        BacktestEngine
                |
                v
        StrategyManager
                |
                v
        TradingSignal
                |
                v
        RiskEngine
                |
                v
        RiskDecision
                |
                v
        ExecutionOrder
                |
                v
        BacktestEngine
                |
                v
        BacktestExecution
                |
                v
        BacktestPortfolio

    This class does not implement:

        - strategy logic
        - risk rules
        - position sizing
        - broker execution
        - persistence
        - Redis
        - PostgreSQL
    """

    def __init__(
        self,
        *,
        engine: BacktestEngine,
        strategy_manager: StrategyManager,
        risk_engine: RiskEngine,
        risk_configuration: BacktestRiskConfiguration,
    ) -> None:
        self.engine = engine
        self.strategy_manager = strategy_manager
        self.risk_engine = risk_engine
        self.risk_configuration = risk_configuration

        self._market_data_view: BacktestMarketDataView | None = None

        self.result = BacktestOrchestrationResult()

        self._current_event: BacktestMarketEvent | None = None
        self._current_candle: BacktestCandle | None = None

    # ==================================================================
    # RUN
    # ==================================================================

    async def run(self) -> BacktestOrchestrationResult:
        """
        Run the complete strategy -> risk -> execution pipeline.

        Lifecycle:

            Strategy runtime starts
                ->
            Backtest strategy instance starts
                ->
            Historical simulation runs
                ->
            Strategy instance stops
                ->
            Strategy runtime stops
        """

        self._configure_callbacks()

        await self.strategy_manager.start()

        strategy_started = False

        try:
            self._validate_strategy_configuration()

            await self.strategy_manager.start_instance(
                self.engine.config.strategy_id,
            )

            strategy_started = True

            await self.engine.run_backtest()

        finally:
            if strategy_started:
                await self._stop_strategy()

            await self.strategy_manager.stop()

        self._sync_execution_results()

        return self.result

    # ==================================================================
    # STRATEGY LIFECYCLE
    # ==================================================================

    def _validate_strategy_configuration(self) -> None:
        """
        Validate that the backtest has a strategy and that the
        corresponding runtime instance was created by composition.
        """

        strategy_id = self.engine.config.strategy_id

        if not strategy_id:
            raise BacktestOrchestrationError(
                "Backtest cannot run without a strategy_id."
            )

        instance = self.strategy_manager.get(strategy_id)

        if instance is None:
            raise BacktestOrchestrationError(
                f"Strategy instance '{strategy_id}' was not created "
                "for this backtest."
            )

    async def _stop_strategy(self) -> None:
        """
        Stop the strategy instance associated with this backtest.
        """

        strategy_id = self.engine.config.strategy_id

        if not strategy_id:
            return

        try:
            await self.strategy_manager.stop_instance(
                strategy_id,
            )

        except Exception as exc:
            self.result.errors.append(
                "Failed to stop backtest strategy "
                f"'{strategy_id}': "
                f"{type(exc).__name__}: {exc}"
            )

    # ==================================================================
    # ENGINE CALLBACK
    # ==================================================================

    def _configure_callbacks(self) -> None:
        """
        Connect BacktestEngine market events to the strategy runtime.
        """

        self.engine.strategy_handler = self._handle_market_event

    async def _handle_market_event(
        self,
        engine: BacktestEngine,
        event: BacktestMarketEvent,
    ) -> None:
        """
        Handle one simulated market event.
        """

        if engine is not self.engine:
            raise BacktestOrchestrationError(
                "Backtest market-event callback received an unexpected "
                "BacktestEngine instance."
            )

        self._current_event = event
        self._current_candle = event.candle

        if self._market_data_view is not None:
            self._market_data_view.set_current_time(
                event.timestamp,
            )

        market_event = self._to_strategy_market_event(
            event.candle,
        )

        signal_events = await self.strategy_manager.dispatcher.dispatch_candle(
            market_event,
        )

        for signal_event in signal_events:
            await self.handle_signal(
                signal_event.signal,
            )

    # ==================================================================
    # SIGNAL
    # ==================================================================

    async def handle_signal(
        self,
        signal: TradingSignal,
    ) -> None:
        """
        Process one strategy signal through RiskEngine and, when
        approved, submit the resulting ExecutionOrder to the
        BacktestEngine.
        """

        self.result.signals_received += 1

        if self._current_candle is None:
            self.result.errors.append(
                "Received strategy signal without a current "
                "backtest candle."
            )
            return

        try:
            decision = self._evaluate_risk(signal)

            self.result.risk_evaluations += 1

            self.result.risk_decisions.append(decision)

            if not decision.approved:
                self.result.rejected_decisions += 1
                return

            self.result.approved_decisions += 1

            execution_order = self._to_execution_order(
                decision,
            )

            self.result.execution_orders += 1

            await self.engine.submit_order(
                execution_order,
                strategy_id=decision.strategy_id,
                strategy_name=decision.strategy_name,
            )

        except Exception as exc:
            traceback.print_exc()

            self.result.errors.append(
                "Signal processing failed: "
                f"{type(exc).__name__}: {exc}"
            )

    # ==================================================================
    # RISK
    # ==================================================================

    def _evaluate_risk(
        self,
        signal: TradingSignal,
    ) -> RiskDecision:
        """
        Build the RiskContext from the current simulated state and
        pass it to the real AQE RiskEngine.

        The RiskContext contains:

        - constraints for the signal symbol
        - constraints for every symbol currently represented by
          an open position

        This allows portfolio exposure calculations to use the
        correct contract specification for every position.
        """

        if self._current_candle is None:
            raise BacktestOrchestrationError(
                "Cannot evaluate risk without a current "
                "backtest candle."
            )

        account = self._build_account_snapshot()

        positions = self._build_position_snapshots()

        market = self._build_market_pricing(
            self._current_candle,
        )

        signal_symbol = signal.symbol.strip().upper()

        # Portfolio exposure can contain multiple symbols.
        # Build constraints for every existing position symbol
        # and always include the symbol of the proposed trade.
        symbols = {
            signal_symbol,
            *(
                position.symbol.strip().upper()
                for position in positions
            ),
        }

        constraints_by_symbol = {
            symbol: self._build_symbol_constraints(symbol)
            for symbol in symbols
        }

        # symbol_constraints remains the constraints specifically
        # associated with the proposed trade.
        symbol_constraints = constraints_by_symbol[signal_symbol]

        context = RiskContext(
            account=account,
            positions=positions,
            symbol_constraints=symbol_constraints,
            constraints_by_symbol=constraints_by_symbol,
            market=market,
            config=self.risk_configuration.config,
            signal=signal,
        )

        return self.risk_engine.evaluate(context)

    # ==================================================================
    # ACCOUNT SNAPSHOT
    # ==================================================================

    def _build_account_snapshot(self) -> AccountRiskSnapshot:
        """
        Convert the backtest portfolio into the account snapshot
        consumed by the Risk Engine.

        The backtest portfolio currently does not model broker margin,
        so margin_level is allowed to remain None. AccountRiskSnapshot
        explicitly supports an optional margin_level.
        """

        self._mark_portfolio_to_market()

        portfolio = self.engine.portfolio

        balance = self._decimal(portfolio.balance)

        equity = self._decimal(portfolio.equity)

        margin = self._decimal(portfolio.margin)

        free_margin = self._decimal(portfolio.free_margin)

        margin_level = (
            self._decimal(portfolio.margin_level)
            if portfolio.margin_level is not None
            else None
        )

        return AccountRiskSnapshot(
            account_id=portfolio.account_id,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            daily_pnl=self._decimal(portfolio.realized_pnl),
            peak_equity=self._decimal(portfolio.peak_equity),
        )

    # ==================================================================
    # POSITIONS
    # ==================================================================

    def _build_position_snapshots(
        self,
    ) -> list[PositionRiskSnapshot]:
        """
        Convert currently open simulated positions into Risk Engine
        position snapshots.

        All monetary and price values crossing into RiskEngine are
        normalized to Decimal here.
        """

        current_prices = self.engine.latest_prices

        snapshots: list[PositionRiskSnapshot] = []

        for position in self.engine.portfolio.open_positions:
            symbol = position.symbol.strip().upper()

            current_price = current_prices.get(
                symbol,
                position.entry_price,
            )

            current_price = self._decimal(current_price)

            direction = (
                SignalDirection.LONG
                if position.side == BacktestPositionSide.LONG
                else SignalDirection.SHORT
            )

            entry_price = self._decimal(position.entry_price)

            quantity = self._decimal(position.volume)

            stop_loss = self._decimal_or_none(
                position.stop_loss,
            )

            take_profit = self._decimal_or_none(
                position.take_profit,
            )

            unrealized_pnl = self._decimal(
                position.unrealized_pnl(
                    current_price,
                )
            )

            snapshots.append(
                PositionRiskSnapshot(
                    position_id=position.position_id,
                    account_id=position.account_id,
                    symbol=symbol,
                    strategy_id=position.strategy_id,
                    direction=direction,
                    quantity=quantity,
                    entry_price=entry_price,
                    current_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    unrealized_pnl=unrealized_pnl,
                    risk_amount=Decimal("0"),
                )
            )

        return snapshots

    # ==================================================================
    # MARKET PRICING
    # ==================================================================

    @staticmethod
    def _build_market_pricing(
        candle: BacktestCandle,
    ) -> MarketPricing:
        """
        Convert historical candle pricing into the bid/ask representation
        required by RiskEngine.

        When spread is unavailable, close is used for both bid and ask.

        When spread is available, it is distributed equally around close.
        """

        close = BacktestOrchestrator._decimal(
            candle.close,
        )

        if candle.spread is None:
            bid = close
            ask = close

        else:
            half_spread = (
                BacktestOrchestrator._decimal(
                    candle.spread,
                )
                / Decimal("2")
            )

            bid = close - half_spread
            ask = close + half_spread

        if bid <= Decimal("0"):
            bid = close

        if ask <= Decimal("0"):
            ask = close

        return MarketPricing(
            bid=bid,
            ask=ask,
        )

    # ==================================================================
    # SYMBOL CONSTRAINTS
    # ==================================================================

    def _build_symbol_constraints(
        self,
        symbol: str,
    ) -> SymbolRiskConstraints:
        """
        Build the symbol constraints required by RiskEngine.

        The backtest uses AQE canonical symbols. Broker-specific
        symbols such as XAUUSD.s are resolved at the broker/account
        boundary and are not used as the backtest symbol namespace.

        XAUUSD currently mirrors the verified MT5 specification for
        XAUUSD.s:

            contract size = 100
            tick size     = 0.01
            tick value    = 1.00
            volume min    = 0.01
            volume max    = 100
            volume step   = 0.01

        These values should eventually come from persisted instrument
        metadata rather than being hard-coded here.
        """

        normalized_symbol = symbol.strip().upper()

        contract_size = self._decimal(
            self.engine.config.contract_sizes.get(
                normalized_symbol,
                Decimal("1"),
            )
        )

        if normalized_symbol == "XAUUSD":
            return SymbolRiskConstraints(
                symbol=normalized_symbol,
                contract_size=Decimal("100"),
                tick_size=Decimal("0.01"),
                tick_value=Decimal("1"),
                volume_min=Decimal("0.01"),
                volume_max=Decimal("100"),
                volume_step=Decimal("0.01"),
                margin_rate=Decimal("1"),
            )

        return SymbolRiskConstraints(
            symbol=normalized_symbol,
            contract_size=contract_size,
            tick_size=Decimal("0.00001"),
            tick_value=Decimal("1"),
            volume_min=Decimal("0.01"),
            volume_max=Decimal("1000"),
            volume_step=Decimal("0.01"),
            margin_rate=Decimal("1"),
        )

    # ==================================================================
    # RISK -> EXECUTION
    # ==================================================================

    @staticmethod
    def _to_execution_order(
        decision: RiskDecision,
    ) -> ExecutionOrder:
        """
        Convert an approved RiskDecision into the shared
        broker-independent ExecutionOrder contract.
        """

        if not decision.approved:
            raise BacktestOrchestrationError(
                "Cannot create ExecutionOrder from a rejected "
                "RiskDecision."
            )

        if decision.position_size is None:
            raise BacktestOrchestrationError(
                "Approved RiskDecision does not contain a "
                "position size."
            )

        if decision.position_size <= Decimal("0"):
            raise BacktestOrchestrationError(
                "Approved RiskDecision contains an invalid "
                "position size."
            )

        if decision.direction == SignalDirection.LONG:
            side = ExecOrderSide.BUY

        elif decision.direction == SignalDirection.SHORT:
            side = ExecOrderSide.SELL

        else:
            raise BacktestOrchestrationError(
                f"Unsupported signal direction: {decision.direction!r}"
            )

        try:
            order_type = ExecOrderType(
                decision.order_type.value.upper(),
            )

        except (AttributeError, ValueError) as exc:
            raise BacktestOrchestrationError(
                "Unsupported execution order type: "
                f"{decision.order_type!r}"
            ) from exc

        price = decision.entry_price

        if (
            order_type
            in {
                ExecOrderType.LIMIT,
                ExecOrderType.STOP,
            }
            and price is None
        ):
            raise BacktestOrchestrationError(
                f"{order_type.value} orders require an entry price."
            )

        strategy_name = (
            decision.strategy_name.strip()
            if decision.strategy_name
            else ""
        )

        comment = (
            f"AQE:{strategy_name}"
            if strategy_name
            else "AQE"
        )

        return ExecutionOrder(
            symbol=decision.symbol,
            account_id=decision.account_id,
            side=side,
            order_type=order_type,
            volume=decision.position_size,
            price=price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            comment=comment[:255],
        )

    # ==================================================================
    # MARKET EVENT ADAPTER
    # ==================================================================

    @staticmethod
    def _to_strategy_market_event(
        candle: BacktestCandle,
    ) -> MarketCandleEvent:
        """
        Convert BacktestCandle into the existing AQE market-data event
        contract consumed by StrategyDispatcher.
        """

        market_candle = MarketCandle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=int(candle.timestamp.timestamp()),
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=int(candle.volume),
            spread=(
                int(candle.spread)
                if candle.spread is not None
                else 0
            ),
        )

        return MarketCandleEvent.create(
            candle=market_candle,
        )

    # ==================================================================
    # PORTFOLIO MARK-TO-MARKET
    # ==================================================================

    def _mark_portfolio_to_market(self) -> None:
        """
        Mark the simulated portfolio using prices maintained by
        BacktestEngine.

        The BacktestEngine may maintain market prices as floats because
        historical market data enters the simulation through the strategy
        market-data layer. Portfolio accounting, however, uses Decimal.

        Therefore the conversion happens at this boundary before prices
        enter portfolio accounting.
        """

        latest_prices = self.engine.latest_prices

        if not latest_prices:
            return

        decimal_prices = {
            symbol.strip().upper(): self._decimal(price)
            for symbol, price in latest_prices.items()
        }

        decimal_contract_sizes = {
            symbol.strip().upper(): self._decimal(contract_size)
            for symbol, contract_size in (
                self.engine.config.contract_sizes.items()
            )
        }

        self.engine.portfolio.mark_to_market(
            prices=decimal_prices,
            contract_sizes=decimal_contract_sizes,
            timestamp=self.engine.run.current_time,
        )

    # ==================================================================
    # RESULT SYNCHRONIZATION
    # ==================================================================

    def _sync_execution_results(self) -> None:
        """
        Copy execution records produced by BacktestEngine into the
        orchestration result.

        BacktestEngine is the source of truth for execution history.
        """

        self.result.executions = list(
            self.engine.run.executions,
        )

    # ==================================================================
    # UTILITIES
    # ==================================================================

    @staticmethod
    def _decimal(
        value: Any,
    ) -> Decimal:
        """
        Convert numeric values to Decimal without inheriting binary
        floating-point representation errors.
        """

        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))

    @staticmethod
    def _decimal_or_none(
        value: Any,
    ) -> Decimal | None:
        """Convert an optional numeric value to Decimal."""

        if value is None:
            return None

        return BacktestOrchestrator._decimal(value)

    def set_market_data_view(
        self,
        market_data_view: BacktestMarketDataView,
    ) -> None:
        """
        Attach the strategy-facing market-data view.

        The view is advanced to each simulated market event before the
        strategy receives that event.
        """

        self._market_data_view = market_data_view

    @staticmethod
    def _margin_level_for_risk(
        *,
        equity: Decimal,
        margin: Decimal,
    ) -> Decimal:
        if margin <= Decimal("0"):
            return Decimal("Infinity")

        return (equity / margin) * Decimal("100")
