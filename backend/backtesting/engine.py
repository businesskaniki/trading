from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)

from .execution import (
    BacktestExecution,
    BacktestExecutionContext,
)
from .fill import (
    BacktestFillConfig,
    BacktestFillEngine,
    BacktestMarket,
)
from .market import (
    BacktestMarketData,
    BacktestMarketEvent,
)
from .orders import (
    BacktestPendingOrderBook,
    PendingBacktestOrder,
)
from .portfolio import BacktestPortfolio


class BacktestEngineError(Exception):
    """Base exception for backtest engine failures."""


class BacktestConfigurationError(BacktestEngineError):
    """Raised when backtest configuration is invalid."""


class BacktestStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """
    Immutable configuration for a backtest.
    """

    account_id: UUID
    initial_balance: Decimal

    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]

    start: datetime | None = None
    end: datetime | None = None

    fill: BacktestFillConfig = field(default_factory=BacktestFillConfig)

    contract_sizes: dict[str, Decimal] = field(default_factory=dict)

    strategy_id: str | None = None
    strategy_name: str | None = None

    close_positions_at_end: bool = True

    def __post_init__(self) -> None:
        if self.initial_balance < Decimal("0"):
            raise BacktestConfigurationError("Initial balance cannot be negative.")

        symbols = tuple(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in self.symbols
                if symbol and symbol.strip()
            )
        )

        timeframes = tuple(
            dict.fromkeys(
                timeframe.strip().upper()
                for timeframe in self.timeframes
                if timeframe and timeframe.strip()
            )
        )

        if not symbols:
            raise BacktestConfigurationError("At least one symbol is required.")

        if not timeframes:
            raise BacktestConfigurationError("At least one timeframe is required.")

        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "timeframes", timeframes)

        start = self._normalize_datetime(self.start)
        end = self._normalize_datetime(self.end)

        if start is not None and end is not None and start >= end:
            raise BacktestConfigurationError(
                "Backtest start must be before backtest end."
            )

        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

        normalized_contract_sizes: dict[str, Decimal] = {}

        for symbol, value in self.contract_sizes.items():
            normalized_symbol = symbol.strip().upper()

            if not normalized_symbol:
                raise BacktestConfigurationError(
                    "Contract-size symbol cannot be empty."
                )

            contract_size = Decimal(str(value))

            if contract_size <= Decimal("0"):
                raise BacktestConfigurationError(
                    f"Contract size for '{normalized_symbol}' "
                    "must be greater than zero."
                )

            normalized_contract_sizes[normalized_symbol] = contract_size

        object.__setattr__(
            self,
            "contract_sizes",
            normalized_contract_sizes,
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class BacktestExecutionRecord:
    """
    Immutable execution record produced during a backtest.
    """

    timestamp: datetime
    order: ExecutionOrder
    result: ExecutionResult

    strategy_id: str | None = None
    strategy_name: str | None = None


@dataclass(slots=True)
class BacktestRun:
    """
    Runtime state and results for one backtest.
    """

    run_id: UUID
    config: BacktestConfig

    status: BacktestStatus = BacktestStatus.CREATED

    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_time: datetime | None = None

    processed_events: int = 0
    processed_candles: int = 0

    executions: list[BacktestExecutionRecord] = field(default_factory=list)

    pending_orders: list[UUID] = field(default_factory=list)

    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BacktestEngine:
    """
    Coordinates the backtest simulation.

    Responsibilities:
        - advance simulation time
        - maintain current market state
        - process pending orders
        - execute approved orders
        - process SL/TP
        - mark the portfolio
        - invoke the strategy/risk orchestration callbacks

    The engine does not contain:
        - strategy logic
        - risk rules
        - broker-specific logic
        - Redis
        - PostgreSQL
    """

    market_data: BacktestMarketData
    config: BacktestConfig

    portfolio: BacktestPortfolio = field(init=False)
    fill_engine: BacktestFillEngine = field(init=False)
    execution: BacktestExecution = field(init=False)
    pending_orders: BacktestPendingOrderBook = field(init=False)
    run: BacktestRun = field(init=False)

    _markets: dict[str, BacktestMarket] = field(
        init=False,
        default_factory=dict,
    )

    _latest_prices: dict[str, Decimal] = field(
        init=False,
        default_factory=dict,
    )

    strategy_handler: (
        Callable[
            ["BacktestEngine", BacktestMarketEvent],
            Awaitable[Any] | Any,
        ]
        | None
    ) = None

    risk_handler: (
        Callable[
            ["BacktestEngine", Any],
            Awaitable[Any] | Any,
        ]
        | None
    ) = None

    def __post_init__(self) -> None:
        self.portfolio = BacktestPortfolio(
            account_id=self.config.account_id,
            initial_balance=self.config.initial_balance,
        )

        self.fill_engine = BacktestFillEngine(
            self.config.fill,
        )

        self.execution = BacktestExecution(
            portfolio=self.portfolio,
            fill_engine=self.fill_engine,
        )

        self.pending_orders = BacktestPendingOrderBook(
            fill_engine=self.fill_engine,
        )

        self.run = BacktestRun(
            run_id=uuid4(),
            config=self.config,
        )

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def run_backtest(self) -> BacktestRun:
        """
        Run the simulation chronologically through the supplied
        historical market data.
        """

        if self.run.status != BacktestStatus.CREATED:
            raise BacktestEngineError(
                "Backtest can only be started from CREATED state."
            )

        self.market_data.finalize()

        self.run.status = BacktestStatus.RUNNING
        self.run.started_at = datetime.now(timezone.utc)

        try:
            events = self.market_data.events(
                symbols=set(self.config.symbols),
                timeframes=set(self.config.timeframes),
                start=self.config.start,
                end=self.config.end,
            )

            for event in events:
                if not self.is_running:
                    break

                await self._process_event(event)

            if self.is_running and self.config.close_positions_at_end:
                await self._close_open_positions()

            if self.is_running:
                self._mark_portfolio_to_market()
                self.run.status = BacktestStatus.COMPLETED

        except Exception as exc:
            self.run.status = BacktestStatus.FAILED
            self.run.errors.append(str(exc))
            raise

        finally:
            self.run.completed_at = datetime.now(timezone.utc)

        return self.run

    def stop(self) -> None:
        """Stop the running backtest."""

        if self.is_running:
            self.run.status = BacktestStatus.STOPPED

    # ==================================================================
    # EVENT PROCESSING
    # ==================================================================

    async def _process_event(
        self,
        event: BacktestMarketEvent,
    ) -> None:
        """
        Process one chronological market event.

        Processing order:

            1. Update clock
            2. Update market state
            3. Trigger pending orders
            4. Check SL/TP
            5. Invoke strategy
            6. Mark portfolio
        """

        self.run.current_time = event.timestamp
        self.run.processed_events += 1
        self.run.processed_candles += 1

        market = self._market_from_event(event)

        self._update_market(market)

        # --------------------------------------------------------------
        # Pending LIMIT / STOP orders
        # --------------------------------------------------------------

        triggered_orders = self.pending_orders.process_market(
            market,
        )

        for pending_order in triggered_orders:
            self._apply_pending_fill(pending_order)

        # --------------------------------------------------------------
        # Existing position SL / TP
        # --------------------------------------------------------------

        exit_results = self.execution.check_position_exits(
            market=market,
            contract_sizes=self.config.contract_sizes,
        )

        self._record_exit_results(
            results=exit_results,
            timestamp=event.timestamp,
        )

        # --------------------------------------------------------------
        # Strategy processing
        # --------------------------------------------------------------

        if self.strategy_handler is not None:
            await self._invoke_callback(
                self.strategy_handler,
                self,
                event,
            )

        # --------------------------------------------------------------
        # Portfolio valuation
        # --------------------------------------------------------------

        self._mark_portfolio_to_market()

    # ==================================================================
    # MARKET STATE
    # ==================================================================

    @staticmethod
    def _market_from_event(
        event: BacktestMarketEvent,
    ) -> BacktestMarket:
        """
        Convert a canonical backtest market event into the market
        representation consumed by the fill engine.
        """

        candle = event.candle

        if candle.spread is None:
            return BacktestMarket(
                candle=candle,
            )

        half_spread = candle.spread / Decimal("2")

        return BacktestMarket(
            candle=candle,
            bid=candle.close - half_spread,
            ask=candle.close + half_spread,
        )

    def _update_market(
        self,
        market: BacktestMarket,
    ) -> None:
        """
        Store the latest market for the symbol.
        """

        symbol = market.candle.symbol.strip().upper()

        self._markets[symbol] = market
        self._latest_prices[symbol] = market.midpoint

    def _store_market(
        self,
        market: BacktestMarket,
    ) -> None:
        """
        Compatibility alias for callers using the previous
        market-storage method.
        """

        self._update_market(market)

    def _current_market_for(
        self,
        symbol: str,
    ) -> BacktestMarket:
        normalized_symbol = symbol.strip().upper()

        try:
            return self._markets[normalized_symbol]
        except KeyError as exc:
            raise BacktestEngineError(
                f"No market data is available for '{normalized_symbol}'."
            ) from exc

    @property
    def current_markets(self) -> dict[str, BacktestMarket]:
        """Return a snapshot of current markets."""

        return dict(self._markets)

    @property
    def latest_prices(self) -> dict[str, Decimal]:
        """Return a snapshot of latest mark prices."""

        return dict(self._latest_prices)

    # ==================================================================
    # ORDER SUBMISSION
    # ==================================================================

    async def submit_order(
        self,
        order: ExecutionOrder,
        *,
        strategy_id: str | None = None,
        strategy_name: str | None = None,
        expiration: datetime | None = None,
    ) -> ExecutionResult | PendingBacktestOrder:
        """
        Submit an ExecutionOrder to the simulated execution environment.

        MARKET:
            execute immediately.

        LIMIT / STOP:
            add to the pending-order book.
        """

        if not self.is_running:
            raise BacktestEngineError(
                "Orders can only be submitted while the backtest is running."
            )

        market = self._current_market_for(order.symbol)

        resolved_strategy_id = (
            strategy_id if strategy_id is not None else self.config.strategy_id
        )

        resolved_strategy_name = (
            strategy_name if strategy_name is not None else self.config.strategy_name
        )

        context = BacktestExecutionContext(
            strategy_id=resolved_strategy_id,
            strategy_name=resolved_strategy_name,
            magic_number=order.magic_number,
        )

        contract_size = self.config.contract_sizes.get(
            order.symbol.strip().upper(),
            Decimal("1"),
        )

        # --------------------------------------------------------------
        # MARKET
        # --------------------------------------------------------------

        if order.order_type == OrderType.MARKET:
            result = self.execution.execute(
                order=order,
                market=market,
                context=context,
                contract_size=contract_size,
            )

            self._record_execution(
                order=order,
                result=result,
                timestamp=market.candle.timestamp,
                strategy_id=resolved_strategy_id,
                strategy_name=resolved_strategy_name,
            )

            self._mark_portfolio_to_market()

            return result

        # --------------------------------------------------------------
        # LIMIT / STOP
        # --------------------------------------------------------------

        pending = self.pending_orders.add(
            order=order,
            created_at=market.candle.timestamp,
            expiration=expiration,
            strategy_id=resolved_strategy_id,
            strategy_name=resolved_strategy_name,
        )

        if pending.order_id not in self.run.pending_orders:
            self.run.pending_orders.append(
                pending.order_id,
            )

        return pending

    # ==================================================================
    # PENDING ORDERS
    # ==================================================================

    def _apply_pending_fill(
        self,
        pending: PendingBacktestOrder,
    ) -> None:
        """
        Apply a fill produced by the pending-order book.

        The pending-order book determines whether the order triggered.
        BacktestExecution owns the conversion of that fill into a
        portfolio position.
        """

        fill = pending.fill

        if fill is None or not fill.is_filled:
            return

        context = BacktestExecutionContext(
            strategy_id=pending.strategy_id,
            strategy_name=pending.strategy_name,
            magic_number=pending.order.magic_number,
        )

        position = self.execution.apply_fill(
            order=pending.order,
            fill=fill,
            context=context,
        )

        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker="BACKTEST",
            broker_order_id=self._uuid_as_int(fill.order_id),
            broker_deal_id=self._uuid_as_int(fill.fill_id),
            broker_position_id=self._uuid_as_int(
                position.position_id,
            ),
            symbol=pending.order.symbol,
            volume=fill.volume,
            price=fill.price,
            message="Pending order filled.",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "position_id": str(position.position_id),
                "fill_reason": fill.reason.value,
            },
        )

        self._record_execution(
            order=pending.order,
            result=result,
            timestamp=fill.timestamp,
            strategy_id=pending.strategy_id,
            strategy_name=pending.strategy_name,
        )

        if pending.order_id in self.run.pending_orders:
            self.run.pending_orders.remove(
                pending.order_id,
            )

    # ==================================================================
    # EXECUTION RECORDING
    # ==================================================================

    def _record_execution(
        self,
        *,
        order: ExecutionOrder,
        result: ExecutionResult,
        timestamp: datetime,
        strategy_id: str | None,
        strategy_name: str | None,
    ) -> None:
        self.run.executions.append(
            BacktestExecutionRecord(
                timestamp=timestamp,
                order=order,
                result=result,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
            )
        )

    def _record_exit_results(
        self,
        *,
        results: list[ExecutionResult],
        timestamp: datetime,
    ) -> None:
        """
        Record internally generated SL/TP executions.
        """

        for result in results:
            position_id = result.broker_position_id

            if position_id is None:
                continue

            position = self._find_closed_position(
                position_id,
            )

            if position is None:
                continue

            order_side = (
                OrderSide.SELL if position.side.value == "LONG" else OrderSide.BUY
            )

            order = ExecutionOrder(
                symbol=position.symbol,
                account_id=position.account_id,
                side=order_side,
                order_type=OrderType.MARKET,
                volume=position.volume,
            )

            self._record_execution(
                order=order,
                result=result,
                timestamp=timestamp,
                strategy_id=position.strategy_id,
                strategy_name=position.strategy_name,
            )

    def _find_closed_position(
        self,
        broker_position_id: int,
    ):
        """
        Find a closed position from its ExecutionResult identifier.
        """

        for position in self.portfolio.closed_positions:
            if self._uuid_as_int(position.position_id) == broker_position_id:
                return position

        return None

    # ==================================================================
    # PORTFOLIO
    # ==================================================================

    def _mark_portfolio_to_market(self) -> None:
        if not self._latest_prices:
            return

        self.portfolio.mark_to_market(
            prices=self._latest_prices,
            contract_sizes=self.config.contract_sizes,
            timestamp=self.run.current_time,
        )

    # ==================================================================
    # END OF BACKTEST
    # ==================================================================

    async def _close_open_positions(self) -> None:
        """
        Close all remaining positions using the latest available market.
        """

        for position in list(self.portfolio.open_positions):
            market = self._current_market_for(
                position.symbol,
            )

            contract_size = self.config.contract_sizes.get(
                position.symbol.strip().upper(),
                Decimal("1"),
            )

            result = self.execution.close_position(
                position_id=position.position_id,
                market=market,
                exit_reason="BACKTEST_END",
                contract_size=contract_size,
            )

            side = OrderSide.SELL if position.side.value == "LONG" else OrderSide.BUY

            order = ExecutionOrder(
                symbol=position.symbol,
                account_id=position.account_id,
                side=side,
                order_type=OrderType.MARKET,
                volume=position.volume,
            )

            self._record_execution(
                order=order,
                result=result,
                timestamp=market.candle.timestamp,
                strategy_id=position.strategy_id,
                strategy_name=position.strategy_name,
            )

    # ==================================================================
    # CALLBACKS
    # ==================================================================

    @staticmethod
    async def _invoke_callback(
        callback: Callable[..., Awaitable[Any] | Any],
        *args: Any,
    ) -> Any:
        result = callback(*args)

        if hasattr(result, "__await__"):
            return await result

        return result

    # ==================================================================
    # STATE / METRICS
    # ==================================================================

    @property
    def is_running(self) -> bool:
        return self.run.status == BacktestStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.run.status == BacktestStatus.COMPLETED

    @property
    def equity(self) -> Decimal:
        return self.portfolio.equity

    @property
    def balance(self) -> Decimal:
        return self.portfolio.balance

    @property
    def realized_pnl(self) -> Decimal:
        return self.portfolio.realized_pnl

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.portfolio.total_unrealized_pnl()

    # ==================================================================
    # COMPATIBILITY
    # ==================================================================

    def _process_market_storage(
        self,
        market: BacktestMarket,
    ) -> None:
        self._store_market(market)

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _uuid_as_int(
        value: UUID,
    ) -> int:
        return value.int % (2**63 - 1)
