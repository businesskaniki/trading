"""Multi-strategy orchestration for the AQE backtesting engine."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

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
from strategies.core.enums import (
    SignalDirection,
    StrategyMode,
    StrategyStatus,
)
from strategies.core.signal import TradingSignal
from strategies.runtime.manager import StrategyManager

from .engine import (
    BacktestEngine,
    BacktestExecutionRecord,
)
from .market import (
    BacktestCandle,
    BacktestMarketEvent,
)
from .market_data_view import BacktestMarketDataView
from .position import BacktestPositionSide

logger = logging.getLogger(__name__)


# ======================================================================
# ERRORS
# ======================================================================


class BacktestOrchestrationError(Exception):
    """Base exception for backtest orchestration failures."""


# ======================================================================
# RISK CONFIGURATION
# ======================================================================


@dataclass(slots=True)
class BacktestRiskConfiguration:
    """
    Risk configuration used by the real AQE RiskEngine.

    The orchestration layer does not implement risk rules. It builds the
    RiskContext and delegates evaluation to RiskEngine.
    """

    config: RiskConfig


# ======================================================================
# STRATEGY RESULT
# ======================================================================


@dataclass(slots=True)
class BacktestStrategyResult:
    """
    Runtime attribution statistics for one strategy.

    These statistics describe one participant inside the shared account
    simulation. They do not represent an independent portfolio.
    """

    strategy_id: str
    strategy_name: str
    signals_received: int = 0
    risk_evaluations: int = 0
    approved_decisions: int = 0
    rejected_decisions: int = 0
    execution_orders: int = 0
    executions: int = 0
    errors: list[str] = field(default_factory=list)


# ======================================================================
# SYMBOL RESULT
# ======================================================================


@dataclass(slots=True)
class BacktestSymbolResult:
    """
    Runtime attribution statistics for one simulated symbol.
    """

    symbol: str
    signals_received: int = 0
    risk_evaluations: int = 0
    approved_decisions: int = 0
    rejected_decisions: int = 0
    execution_orders: int = 0
    executions: int = 0


# ======================================================================
# ORCHESTRATION RESULT
# ======================================================================


@dataclass(slots=True)
class BacktestOrchestrationResult:
    """
    Results produced by the account-level:

        Strategy
            ->
        Risk
            ->
        Execution

    pipeline.

    The strategy_results and symbol_results mappings are attribution
    views over one shared BacktestPortfolio.
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
    strategy_results: dict[str, BacktestStrategyResult] = field(
        default_factory=dict,
    )
    symbol_results: dict[str, BacktestSymbolResult] = field(
        default_factory=dict,
    )
    errors: list[str] = field(
        default_factory=list,
    )


# ======================================================================
# ORCHESTRATOR
# ======================================================================


class BacktestOrchestrator:
    """
    Integrate Strategy Runtime, Risk Engine, and Backtest Execution
    Engine for one account-level multi-strategy backtest.

    Architecture:

        Historical Market Data
                |
                v
        BacktestEngine
                |
                v
        StrategyManager
           /     |     \
          /      |      \
    Strategy A  ...  Strategy N
          \      |      /
           \     |     /
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
       Shared BacktestPortfolio

    Responsibilities:

        - coordinate isolated strategy instances
        - advance the backtest market-data view
        - route historical candle events
        - pass TradingSignal into the real RiskEngine
        - convert approved RiskDecision into ExecutionOrder
        - submit orders to BacktestEngine
        - maintain strategy and symbol attribution

    It does not implement:

        - strategy logic
        - risk rules
        - position sizing rules
        - broker execution
        - historical loading
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
        strategy_ids: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.engine = engine
        self.strategy_manager = strategy_manager
        self.risk_engine = risk_engine
        self.risk_configuration = risk_configuration
        self.strategy_ids = self._normalize_strategy_ids(
            strategy_ids,
        )

        self._market_data_view: BacktestMarketDataView | None = None
        self.result = BacktestOrchestrationResult()
        self._current_event: BacktestMarketEvent | None = None
        self._current_candle: BacktestCandle | None = None
        self._strategies_started = False

    # ==================================================================
    # RUN
    # ==================================================================

    async def run(
        self,
    ) -> BacktestOrchestrationResult:
        """
        Run the complete account-level multi-strategy pipeline.

        Lifecycle:

            configure callback
                ->
            start StrategyManager
                ->
            validate strategy instances
                ->
            start strategy instances
                ->
            run historical simulation
                ->
            stop strategy instances
                ->
            stop StrategyManager
                ->
            synchronize execution history
        """

        self._configure_callbacks()

        await self.strategy_manager.start()

        simulation_error: BaseException | None = None

        try:
            self._validate_strategy_configuration()

            await self._start_strategies()

            await self.engine.run_backtest()

        except BaseException as exc:
            simulation_error = exc
            raise

        finally:
            try:
                await self._stop_strategies()

            except Exception as exc:
                message = (
                    "Strategy shutdown failed after backtest execution: "
                    f"{type(exc).__name__}: {exc}"
                )

                logger.exception(
                    "%s",
                    message,
                )

                self.result.errors.append(
                    message,
                )

                if simulation_error is None:
                    raise

            finally:
                try:
                    await self.strategy_manager.stop()

                except Exception as exc:
                    message = (
                        "StrategyManager shutdown failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

                    logger.exception(
                        "%s",
                        message,
                    )

                    self.result.errors.append(
                        message,
                    )

                    if simulation_error is None:
                        raise

        self._sync_execution_results()

        return self.result

    # ==================================================================
    # STRATEGY CONFIGURATION
    # ==================================================================

    def _validate_strategy_configuration(
        self,
    ) -> None:
        """
        Validate every resolved strategy instance.

        Every participating strategy must:

            - exist in StrategyManager
            - run in BACKTEST mode
            - be enabled
            - be initialized and active
        """

        if not self.strategy_ids:
            raise BacktestOrchestrationError(
                "Backtest cannot run without at least one resolved " "active strategy.",
            )

        for strategy_id in self.strategy_ids:
            instance = self.strategy_manager.dispatcher.get_instance(
                strategy_id,
            )

            if instance is None:
                raise BacktestOrchestrationError(
                    f"Strategy instance '{strategy_id}' was not created "
                    "for this backtest.",
                )

            if instance.mode != StrategyMode.BACKTEST:
                raise BacktestOrchestrationError(
                    f"Strategy '{strategy_id}' must run in BACKTEST mode.",
                )

            if not instance.config.enabled:
                raise BacktestOrchestrationError(
                    f"Strategy '{strategy_id}' is disabled.",
                )

            if not instance.is_active:
                raise BacktestOrchestrationError(
                    f"Strategy '{strategy_id}' is not active. "
                    f"Current status: {instance.status!r}.",
                )

            self._ensure_strategy_result(
                strategy_id=strategy_id,
                strategy_name=instance.strategy_name,
            )

    # ==================================================================
    # STRATEGY LIFECYCLE
    # ==================================================================

    async def _start_strategies(
        self,
    ) -> None:
        """
        Start every resolved strategy instance.

        All instances participate in the same simulated account and
        shared portfolio.
        """

        started: list[str] = []

        try:
            for strategy_id in self.strategy_ids:
                await self.strategy_manager.start_instance(
                    strategy_id,
                )

                started.append(
                    strategy_id,
                )

            self._strategies_started = True

            logger.info(
                "Backtest strategies started: run_id=%s strategies=%s",
                self.engine.run.run_id,
                self.strategy_ids,
            )

        except Exception:
            for strategy_id in reversed(started):
                try:
                    await self.strategy_manager.stop_instance(
                        strategy_id,
                    )

                except Exception:
                    logger.exception(
                        "Failed to clean up strategy after startup " "failure: id=%s",
                        strategy_id,
                    )

            self._strategies_started = False
            raise

    async def _stop_strategies(
        self,
    ) -> None:
        """
        Stop every strategy participating in the backtest.

        The lifecycle check uses StrategyStatus directly rather than
        comparing enum values as strings.
        """

        if not self.strategy_ids:
            self._strategies_started = False
            return

        for strategy_id in reversed(
            self.strategy_ids,
        ):
            instance = self.strategy_manager.dispatcher.get_instance(
                strategy_id,
            )

            if instance is None:
                continue

            if instance.status in {
                StrategyStatus.STOPPED,
                StrategyStatus.CREATED,
            }:
                continue

            try:
                await self.strategy_manager.stop_instance(
                    strategy_id,
                )

            except Exception as exc:
                message = (
                    "Failed to stop backtest strategy "
                    f"'{strategy_id}': "
                    f"{type(exc).__name__}: {exc}"
                )

                logger.exception(
                    "%s",
                    message,
                )

                self.result.errors.append(
                    message,
                )

                strategy_result = self.result.strategy_results.get(
                    strategy_id,
                )

                if strategy_result is not None:
                    strategy_result.errors.append(
                        message,
                    )

        self._strategies_started = False

    # ==================================================================
    # ENGINE CALLBACK
    # ==================================================================

    def _configure_callbacks(
        self,
    ) -> None:
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
        Handle one historical market event.

        The simulation clock is advanced before the StrategyDispatcher
        receives the candle so strategies can only see data available
        at the current simulated timestamp.
        """

        if engine is not self.engine:
            raise BacktestOrchestrationError(
                "Backtest market-event callback received an "
                "unexpected BacktestEngine instance.",
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

        # Deterministic ordering ensures that multiple strategies
        # producing signals on the same candle are processed in a
        # stable order.
        ordered_signal_events = sorted(
            signal_events,
            key=self._signal_sort_key,
        )

        for signal_event in ordered_signal_events:
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
        Process one TradingSignal through:

            RiskEngine
                ->
            RiskDecision
                ->
            ExecutionOrder
                ->
            BacktestEngine
        """

        self.result.signals_received += 1

        strategy_id = signal.strategy_id.strip() if signal.strategy_id else ""

        if not strategy_id:
            message = "Received a trading signal without a strategy_id."

            self.result.errors.append(
                message,
            )

            logger.error(
                "%s",
                message,
            )

            return

        if strategy_id not in self.strategy_ids:
            message = (
                "Received a signal from non-participating strategy " f"'{strategy_id}'."
            )

            self.result.errors.append(
                message,
            )

            logger.error(
                "%s",
                message,
            )

            return

        strategy_name = (
            signal.strategy_name.strip() if signal.strategy_name else strategy_id
        )

        strategy_result = self._ensure_strategy_result(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
        )

        symbol = signal.symbol.strip().upper()

        if not symbol:
            message = (
                f"Strategy '{strategy_id}' produced a signal with " "an empty symbol."
            )

            self.result.errors.append(
                message,
            )

            strategy_result.errors.append(
                message,
            )

            return

        symbol_result = self._ensure_symbol_result(
            symbol,
        )

        strategy_result.signals_received += 1
        symbol_result.signals_received += 1

        if self._current_candle is None:
            message = "Received strategy signal without a current " "backtest candle."

            self.result.errors.append(
                message,
            )

            strategy_result.errors.append(
                message,
            )

            return

        try:
            decision = self._evaluate_risk(
                signal,
            )

            self.result.risk_evaluations += 1
            strategy_result.risk_evaluations += 1
            symbol_result.risk_evaluations += 1

            self.result.risk_decisions.append(
                decision,
            )

            if not decision.approved:
                self.result.rejected_decisions += 1
                strategy_result.rejected_decisions += 1
                symbol_result.rejected_decisions += 1
                return

            self.result.approved_decisions += 1
            strategy_result.approved_decisions += 1
            symbol_result.approved_decisions += 1

            execution_order = self._to_execution_order(
                decision,
            )

            self.result.execution_orders += 1
            strategy_result.execution_orders += 1
            symbol_result.execution_orders += 1

            await self.engine.submit_order(
                execution_order,
                strategy_id=decision.strategy_id,
                strategy_name=decision.strategy_name,
            )

        except Exception as exc:
            message = "Signal processing failed: " f"{type(exc).__name__}: {exc}"

            logger.exception(
                "Backtest signal processing failed: " "strategy=%s symbol=%s",
                strategy_id,
                symbol,
            )

            self.result.errors.append(
                message,
            )

            strategy_result.errors.append(
                message,
            )

    # ==================================================================
    # RISK
    # ==================================================================

    def _evaluate_risk(
        self,
        signal: TradingSignal,
    ) -> RiskDecision:
        """
        Build the complete account-level RiskContext and evaluate it
        using the production RiskEngine.

        The context contains all open positions across all participating
        strategies, allowing account-level exposure rules to operate
        against the shared portfolio.
        """

        if self._current_candle is None:
            raise BacktestOrchestrationError(
                "Cannot evaluate risk without a current " "backtest candle.",
            )

        account = self._build_account_snapshot()
        positions = self._build_position_snapshots()

        signal_symbol = signal.symbol.strip().upper()

        if not signal_symbol:
            raise BacktestOrchestrationError(
                "Risk evaluation requires a non-empty signal symbol.",
            )

        symbols = {
            signal_symbol,
            *(
                position.symbol.strip().upper()
                for position in self.engine.portfolio.open_positions
            ),
        }

        constraints_by_symbol = {
            symbol: self._build_symbol_constraints(
                symbol,
            )
            for symbol in symbols
        }

        symbol_constraints = constraints_by_symbol[signal_symbol]

        market = self._build_market_pricing(
            self._current_candle,
        )

        context = RiskContext(
            account=account,
            positions=positions,
            symbol_constraints=symbol_constraints,
            constraints_by_symbol=constraints_by_symbol,
            market=market,
            config=self.risk_configuration.config,
            signal=signal,
        )

        return self.risk_engine.evaluate(
            context,
        )

    # ==================================================================
    # ACCOUNT SNAPSHOT
    # ==================================================================

    def _build_account_snapshot(
        self,
    ) -> AccountRiskSnapshot:
        """
        Convert the shared backtest portfolio into RiskEngine account
        state.

        Equity is explicitly:

            balance + unrealized P&L
        """

        portfolio = self.engine.portfolio

        balance = self._decimal(
            portfolio.balance,
        )

        unrealized = self._calculate_unrealized_pnl()

        equity = balance + unrealized

        margin = self._decimal(
            portfolio.margin,
        )

        # The current backtest portfolio does not model broker-reserved
        # margin, so free margin equals marked equity.
        free_margin = equity

        margin_level = (
            (equity / margin) * Decimal("100") if margin > Decimal("0") else None
        )

        return AccountRiskSnapshot(
            account_id=portfolio.account_id,
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            daily_pnl=self._decimal(
                portfolio.realized_pnl,
            ),
            peak_equity=self._decimal(
                portfolio.peak_equity,
            ),
        )

    def _calculate_unrealized_pnl(
        self,
    ) -> Decimal:
        """
        Calculate floating P&L for every open position in the shared
        portfolio using the same resolved contract sizes used elsewhere
        in the backtest.
        """

        portfolio = self.engine.portfolio

        if not portfolio.open_positions:
            return Decimal("0")

        latest_prices = self.engine.latest_prices

        if not latest_prices:
            return Decimal("0")

        prices = {
            symbol.strip().upper(): self._decimal(
                price,
            )
            for symbol, price in latest_prices.items()
        }

        return portfolio.total_unrealized_pnl(
            prices=prices,
            contract_sizes=self._resolved_contract_sizes(),
        )

    # ==================================================================
    # POSITIONS
    # ==================================================================

    def _build_position_snapshots(
        self,
    ) -> list[PositionRiskSnapshot]:
        """
        Convert every open simulated position into a RiskEngine
        PositionRiskSnapshot.

        Positions from all strategies are included together.
        """

        current_prices = {
            symbol.strip().upper(): self._decimal(price)
            for symbol, price in self.engine.latest_prices.items()
        }

        snapshots: list[PositionRiskSnapshot] = []

        for position in self.engine.portfolio.open_positions:
            symbol = position.symbol.strip().upper()

            current_price = current_prices.get(
                symbol,
                self._decimal(
                    position.entry_price,
                ),
            )

            direction = (
                SignalDirection.LONG
                if position.side == BacktestPositionSide.LONG
                else SignalDirection.SHORT
            )

            entry_price = self._decimal(
                position.entry_price,
            )

            quantity = self._decimal(
                position.volume,
            )

            stop_loss = self._decimal_or_none(
                position.stop_loss,
            )

            take_profit = self._decimal_or_none(
                position.take_profit,
            )

            contract_size = self._contract_size(
                symbol,
            )

            unrealized_pnl = position.unrealized_pnl(
                current_price=current_price,
                contract_size=contract_size,
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
                    unrealized_pnl=self._decimal(
                        unrealized_pnl,
                    ),
                    risk_amount=Decimal("0"),
                ),
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
        Convert the current candle into RiskEngine market pricing.

        Historical candle spread is not interpreted as a price delta.

        Until explicit historical bid/ask data exists, the close is used
        for both bid and ask.
        """

        close = BacktestOrchestrator._decimal(
            candle.close,
        )

        if close <= Decimal("0"):
            raise BacktestOrchestrationError(
                f"Invalid market close for {candle.symbol}: {close}",
            )

        return MarketPricing(
            bid=close,
            ask=close,
        )

    # ==================================================================
    # SYMBOL CONSTRAINTS
    # ==================================================================

    def _build_symbol_constraints(
        self,
        symbol: str,
    ) -> SymbolRiskConstraints:
        """
        Build symbol constraints consumed by RiskEngine.

        Configured contract sizes take precedence.

        XAUUSD / XAUUSD.s currently use the verified AQE gold
        backtest constraints.
        """

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise BacktestOrchestrationError(
                "Symbol constraints require a non-empty symbol.",
            )

        contract_size = self._contract_size(
            normalized_symbol,
        )

        if normalized_symbol in {
            "XAUUSD",
            "XAUUSD.S",
        }:
            return SymbolRiskConstraints(
                symbol=normalized_symbol,
                contract_size=contract_size,
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
                "Cannot create ExecutionOrder from a rejected " "RiskDecision.",
            )

        if decision.position_size is None:
            raise BacktestOrchestrationError(
                "Approved RiskDecision does not contain a " "position size.",
            )

        position_size = BacktestOrchestrator._decimal(
            decision.position_size,
        )

        if position_size <= Decimal("0"):
            raise BacktestOrchestrationError(
                "Approved RiskDecision contains an invalid " "position size.",
            )

        if decision.direction == SignalDirection.LONG:
            side = ExecOrderSide.BUY

        elif decision.direction == SignalDirection.SHORT:
            side = ExecOrderSide.SELL

        else:
            raise BacktestOrchestrationError(
                f"Unsupported signal direction: {decision.direction!r}",
            )

        try:
            order_type = ExecOrderType(
                decision.order_type.value.upper(),
            )

        except (AttributeError, ValueError) as exc:
            raise BacktestOrchestrationError(
                "Unsupported execution order type: " f"{decision.order_type!r}",
            ) from exc

        price = (
            BacktestOrchestrator._decimal(
                decision.entry_price,
            )
            if decision.entry_price is not None
            else None
        )

        if (
            order_type
            in {
                ExecOrderType.LIMIT,
                ExecOrderType.STOP,
            }
            and price is None
        ):
            raise BacktestOrchestrationError(
                f"{order_type.value} orders require an entry price.",
            )

        stop_loss = (
            BacktestOrchestrator._decimal(
                decision.stop_loss,
            )
            if decision.stop_loss is not None
            else None
        )

        take_profit = (
            BacktestOrchestrator._decimal(
                decision.take_profit,
            )
            if decision.take_profit is not None
            else None
        )

        strategy_name = decision.strategy_name.strip() if decision.strategy_name else ""

        comment = f"AQE:{strategy_name}" if strategy_name else "AQE"

        return ExecutionOrder(
            symbol=decision.symbol.strip().upper(),
            account_id=decision.account_id,
            side=side,
            order_type=order_type,
            volume=position_size,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
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
        Convert canonical BacktestCandle into the AQE market-data event
        contract consumed by StrategyDispatcher.
        """

        market_candle = MarketCandle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=int(
                candle.timestamp.timestamp(),
            ),
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=int(candle.volume),
            spread=(int(candle.spread) if candle.spread is not None else 0),
        )

        return MarketCandleEvent.create(
            candle=market_candle,
        )

    # ==================================================================
    # PORTFOLIO MARK-TO-MARKET
    # ==================================================================

    def _mark_portfolio_to_market(
        self,
    ) -> Decimal:
        """
        Mark the shared account portfolio using the latest known prices.

        Contract sizes are resolved through the same central helper used
        by risk calculations and position snapshots.
        """

        latest_prices = self.engine.latest_prices

        if not latest_prices:
            return self._decimal(
                self.engine.portfolio.balance,
            )

        decimal_prices = {
            symbol.strip().upper(): self._decimal(price)
            for symbol, price in latest_prices.items()
        }

        return self.engine.portfolio.mark_to_market(
            prices=decimal_prices,
            contract_sizes=self._resolved_contract_sizes(),
            timestamp=self.engine.run.current_time,
        )

    # ==================================================================
    # RESULT SYNCHRONIZATION
    # ==================================================================

    def _sync_execution_results(
        self,
    ) -> None:
        """
        Synchronize authoritative execution history from BacktestEngine.

        This is necessary because pending LIMIT/STOP orders are submitted
        at one simulated timestamp and may fill on a later market event.
        """

        self.result.executions = list(
            self.engine.run.executions,
        )

        # Reset execution attribution before rebuilding it from the
        # engine's authoritative records.
        for strategy_result in self.result.strategy_results.values():
            strategy_result.executions = 0

        for symbol_result in self.result.symbol_results.values():
            symbol_result.executions = 0

        for execution in self.result.executions:
            strategy_id = execution.strategy_id

            if strategy_id:
                strategy_result = self.result.strategy_results.get(
                    strategy_id,
                )

                if strategy_result is None:
                    strategy_result = BacktestStrategyResult(
                        strategy_id=strategy_id,
                        strategy_name=(execution.strategy_name or strategy_id),
                    )

                    self.result.strategy_results[strategy_id] = strategy_result

                strategy_result.executions += 1

            symbol = execution.order.symbol.strip().upper()

            symbol_result = self._ensure_symbol_result(
                symbol,
            )

            symbol_result.executions += 1

    # ==================================================================
    # RESULT HELPERS
    # ==================================================================

    def _ensure_strategy_result(
        self,
        *,
        strategy_id: str,
        strategy_name: str,
    ) -> BacktestStrategyResult:
        """
        Return or create strategy attribution state.
        """

        normalized_id = strategy_id.strip()

        if not normalized_id:
            raise BacktestOrchestrationError(
                "Strategy result requires a non-empty strategy ID.",
            )

        existing = self.result.strategy_results.get(
            normalized_id,
        )

        if existing is not None:
            return existing

        normalized_name = strategy_name.strip() if strategy_name else normalized_id

        result = BacktestStrategyResult(
            strategy_id=normalized_id,
            strategy_name=normalized_name,
        )

        self.result.strategy_results[normalized_id] = result

        return result

    def _ensure_symbol_result(
        self,
        symbol: str,
    ) -> BacktestSymbolResult:
        """
        Return or create symbol attribution state.
        """

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise BacktestOrchestrationError(
                "Symbol result requires a non-empty symbol.",
            )

        existing = self.result.symbol_results.get(
            normalized_symbol,
        )

        if existing is not None:
            return existing

        result = BacktestSymbolResult(
            symbol=normalized_symbol,
        )

        self.result.symbol_results[normalized_symbol] = result

        return result

    # ==================================================================
    # CONTRACT SIZE
    # ==================================================================

    def _resolved_contract_sizes(self) -> dict[str, Decimal]:
        """
        Resolve contract sizes for all symbols participating in the
        current account-level backtest.

        Explicit account-specific configuration takes precedence.

        The XAUUSD fallback remains for compatibility with older
        BacktestConfig objects that were created before AccountSymbol
        metadata was propagated into the composition layer.
        """

        symbols = self.engine.config.symbols

        configured = {
            symbol.strip().upper(): self._decimal(contract_size)
            for symbol, contract_size in self.engine.config.contract_sizes.items()
        }

        resolved: dict[str, Decimal] = {}

        for symbol in symbols:
            normalized_symbol = symbol.strip().upper()

            if not normalized_symbol:
                continue

            if normalized_symbol in configured:
                resolved[normalized_symbol] = configured[normalized_symbol]
                continue

            if normalized_symbol in {
                "XAUUSD",
                "XAUUSD.S",
            }:
                resolved[normalized_symbol] = Decimal("100")
                continue

            resolved[normalized_symbol] = Decimal("1")

        # Include explicitly configured symbols even when they are not
        # present in config.symbols. This keeps the helper safe for
        # compatibility with manually constructed BacktestConfig values.
        for symbol, contract_size in configured.items():
            resolved.setdefault(
                symbol,
                contract_size,
            )

        return resolved

    def _contract_size(
        self,
        symbol: str,
    ) -> Decimal:
        """
        Return the resolved contract size for one symbol.
        """

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise BacktestOrchestrationError(
                "Contract-size lookup requires a non-empty symbol.",
            )

        contract_sizes = self._resolved_contract_sizes()

        configured = contract_sizes.get(
            normalized_symbol,
        )

        if configured is not None:
            return configured

        if normalized_symbol in {
            "XAUUSD",
            "XAUUSD.S",
        }:
            return Decimal("100")

        return Decimal("1")

    # ==================================================================
    # UTILITIES
    # ==================================================================

    @staticmethod
    def _normalize_strategy_ids(
        strategy_ids: Iterable[str] | None,
    ) -> tuple[str, ...]:
        """
        Normalize and deduplicate strategy IDs while preserving order.
        """

        if strategy_ids is None:
            return ()

        normalized: list[str] = []
        seen: set[str] = set()

        for strategy_id in strategy_ids:
            if not isinstance(
                strategy_id,
                str,
            ):
                raise TypeError(
                    "strategy_ids must contain strings.",
                )

            value = strategy_id.strip()

            if not value or value in seen:
                continue

            seen.add(value)
            normalized.append(value)

        return tuple(
            normalized,
        )

    @staticmethod
    def _signal_sort_key(
        signal_event: Any,
    ) -> tuple[Any, str, str]:
        """
        Return a deterministic ordering key for strategy signals.
        """

        signal = signal_event.signal

        return (
            signal.timestamp,
            (signal.strategy_id.strip() if signal.strategy_id else ""),
            (signal.symbol.strip().upper() if signal.symbol else ""),
        )

    @staticmethod
    def _decimal(
        value: Any,
    ) -> Decimal:
        """
        Convert a numeric value into a finite Decimal.

        Decimal values are returned unchanged. Other values are converted
        through str() to avoid importing binary floating-point artifacts
        into financial calculations.
        """

        if isinstance(
            value,
            Decimal,
        ):
            result = value

        elif value is None:
            raise ValueError(
                "None cannot be converted to Decimal.",
            )

        else:
            result = Decimal(
                str(value),
            )

        if not result.is_finite():
            raise ValueError(
                f"Decimal value must be finite: {value!r}",
            )

        return result

    @staticmethod
    def _decimal_or_none(
        value: Any,
    ) -> Decimal | None:
        """
        Convert an optional numeric value into Decimal.
        """

        if value is None:
            return None

        return BacktestOrchestrator._decimal(
            value,
        )

    def set_market_data_view(
        self,
        market_data_view: BacktestMarketDataView,
    ) -> None:
        """
        Attach the simulation-aware strategy market-data view.
        """

        if not isinstance(
            market_data_view,
            BacktestMarketDataView,
        ):
            raise TypeError(
                "market_data_view must be a BacktestMarketDataView.",
            )

        self._market_data_view = market_data_view
