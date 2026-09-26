from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)

from .fill import (
    BacktestFill,
    BacktestFillEngine,
    BacktestMarket,
)
from .market import BacktestCandle
from .position import (
    BacktestPosition,
    BacktestPositionSide,
)
from .portfolio import BacktestPortfolio


class BacktestExecutionError(Exception):
    """Base exception for backtest execution failures."""


class BacktestOrderRejectedError(BacktestExecutionError):
    """Raised when a backtest order cannot be executed."""


@dataclass(frozen=True, slots=True)
class BacktestExecutionContext:
    """
    Execution metadata associated with a strategy order.
    """

    strategy_id: str | None = None
    strategy_name: str | None = None
    magic_number: int = 10001


class BacktestExecution:
    """
    Executes AQE ExecutionOrder contracts against a simulated portfolio.

    Responsibilities:

        ExecutionOrder
            ↓
        FillEngine
            ↓
        BacktestFill
            ↓
        BacktestPosition
            ↓
        Portfolio

    This class does not know about:
        - strategies
        - RiskEngine
        - Redis
        - PostgreSQL
        - MT5
    """

    def __init__(
        self,
        portfolio: BacktestPortfolio,
        fill_engine: BacktestFillEngine,
    ) -> None:
        self.portfolio = portfolio
        self.fill_engine = fill_engine

    # ------------------------------------------------------------------
    # ORDER EXECUTION
    # ------------------------------------------------------------------

    def execute(
        self,
        *,
        order: ExecutionOrder,
        market: BacktestMarket,
        context: BacktestExecutionContext | None = None,
        order_id: UUID | None = None,
        contract_size: Decimal = Decimal("1"),
    ) -> ExecutionResult:
        """
        Execute an immediately executable order.

        MARKET orders are supported here.

        LIMIT and STOP orders must go through
        BacktestPendingOrderBook first.
        """

        if order.account_id != self.portfolio.account_id:
            raise BacktestOrderRejectedError(
                "Order account does not match the backtest portfolio."
            )

        if contract_size <= Decimal("0"):
            raise BacktestExecutionError("Contract size must be greater than zero.")

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise BacktestOrderRejectedError(
                "LIMIT and STOP orders must be submitted through "
                "the pending-order book."
            )

        fill = self.fill_engine.execute(
            order=order,
            market=market,
            order_id=order_id,
        )

        if not fill.is_filled:
            return self._not_filled_result(
                order=order,
                fill=fill,
            )

        position = self.apply_fill(
            order=order,
            fill=fill,
            context=context,
        )

        return self._success_result(
            order=order,
            fill=fill,
            position=position,
        )

    # ------------------------------------------------------------------
    # APPLY FILL
    # ------------------------------------------------------------------

    def apply_fill(
        self,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
        context: BacktestExecutionContext | None = None,
    ) -> BacktestPosition:
        """
        Apply an already-generated fill.

        Used by pending LIMIT/STOP orders.

        The fill engine is NOT called again.
        """

        if not fill.is_filled:
            raise BacktestExecutionError("Cannot apply a fill that is not FILLED.")

        if order.account_id != self.portfolio.account_id:
            raise BacktestOrderRejectedError(
                "Order account does not match the backtest portfolio."
            )

        if fill.symbol.upper() != order.symbol.upper():
            raise BacktestExecutionError("Fill symbol does not match order symbol.")

        if fill.volume != order.volume:
            raise BacktestExecutionError("Fill volume does not match order volume.")

        strategy_id = context.strategy_id if context is not None else None

        strategy_name = context.strategy_name if context is not None else None

        position = BacktestPosition.open(
            account_id=self.portfolio.account_id,
            symbol=order.symbol,
            side=self._position_side(order.side),
            volume=fill.volume,
            entry_price=fill.price,
            opened_at=fill.timestamp,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
        )

        self.portfolio.add_position(position)

        return position

    # ------------------------------------------------------------------
    # POSITION CLOSING
    # ------------------------------------------------------------------

    def close_position(
        self,
        *,
        position_id: UUID,
        market: BacktestMarket,
        exit_reason: str = "MANUAL",
        contract_size: Decimal = Decimal("1"),
    ) -> ExecutionResult:
        """
        Close an existing simulated position.
        """

        if contract_size <= Decimal("0"):
            raise BacktestExecutionError("Contract size must be greater than zero.")

        position = self.portfolio.get_position(
            position_id,
        )

        if position is None:
            raise BacktestExecutionError(f"Position '{position_id}' does not exist.")

        if not position.is_open:
            raise BacktestExecutionError(f"Position '{position_id}' is already closed.")

        side = (
            OrderSide.SELL
            if position.side == BacktestPositionSide.LONG
            else OrderSide.BUY
        )

        order = ExecutionOrder(
            symbol=position.symbol,
            account_id=position.account_id,
            side=side,
            order_type=OrderType.MARKET,
            volume=position.volume,
        )

        fill = self.fill_engine.execute(
            order=order,
            market=market,
        )

        if not fill.is_filled:
            return self._not_filled_result(
                order=order,
                fill=fill,
            )

        self.portfolio.close_position(
            position_id=position_id,
            exit_price=fill.price,
            closed_at=fill.timestamp,
            commission=fill.commission,
            swap=Decimal("0"),
            exit_reason=exit_reason,
            contract_size=contract_size,
        )

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker="BACKTEST",
            broker_order_id=self._uuid_as_int(
                fill.order_id,
            ),
            broker_deal_id=self._uuid_as_int(
                fill.fill_id,
            ),
            broker_position_id=self._uuid_as_int(
                position_id,
            ),
            symbol=position.symbol,
            volume=position.volume,
            price=fill.price,
            message=f"Position closed: {exit_reason}",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "position_id": str(position_id),
                "exit_reason": exit_reason,
            },
        )

    # ------------------------------------------------------------------
    # SL / TP
    # ------------------------------------------------------------------

    def check_position_exits(
        self,
        *,
        market: BacktestMarket,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> list[ExecutionResult]:
        """
        Check open positions against the current candle.

        When both SL and TP are touched in one candle, SL wins
        conservatively.
        """

        results: list[ExecutionResult] = []

        contract_sizes = contract_sizes or {}

        for position in list(
            self.portfolio.open_positions,
        ):
            if position.symbol.upper() != market.candle.symbol.upper():
                continue

            trigger = self._resolve_exit_trigger(
                position=position,
                candle=market.candle,
            )

            if trigger is None:
                continue

            exit_price, reason = trigger

            result = self._close_position_at_trigger(
                position=position,
                exit_price=exit_price,
                timestamp=market.candle.timestamp,
                reason=reason,
                contract_size=contract_sizes.get(
                    position.symbol.upper(),
                    Decimal("1"),
                ),
            )

            results.append(result)

        return results

    def _resolve_exit_trigger(
        self,
        *,
        position: BacktestPosition,
        candle: BacktestCandle,
    ) -> tuple[Decimal, str] | None:
        if position.side == BacktestPositionSide.LONG:
            if position.stop_loss is not None and candle.low <= position.stop_loss:
                return (
                    position.stop_loss,
                    "STOP_LOSS",
                )

            if position.take_profit is not None and candle.high >= position.take_profit:
                return (
                    position.take_profit,
                    "TAKE_PROFIT",
                )

        else:
            if position.stop_loss is not None and candle.high >= position.stop_loss:
                return (
                    position.stop_loss,
                    "STOP_LOSS",
                )

            if position.take_profit is not None and candle.low <= position.take_profit:
                return (
                    position.take_profit,
                    "TAKE_PROFIT",
                )

        return None

    def _close_position_at_trigger(
        self,
        *,
        position: BacktestPosition,
        exit_price: Decimal,
        timestamp,
        reason: str,
        contract_size: Decimal,
    ) -> ExecutionResult:
        if contract_size <= Decimal("0"):
            raise BacktestExecutionError("Contract size must be greater than zero.")

        commission = position.volume * self.fill_engine.config.commission_per_volume

        self.portfolio.close_position(
            position_id=position.position_id,
            exit_price=exit_price,
            closed_at=timestamp,
            commission=commission,
            swap=Decimal("0"),
            exit_reason=reason,
            contract_size=contract_size,
        )

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker="BACKTEST",
            broker_order_id=self._uuid_as_int(
                position.position_id,
            ),
            broker_deal_id=self._uuid_as_int(
                position.position_id,
            ),
            broker_position_id=self._uuid_as_int(
                position.position_id,
            ),
            symbol=position.symbol,
            volume=position.volume,
            price=exit_price,
            message=f"Position closed by {reason}.",
            raw_response={
                "position_id": str(position.position_id),
                "exit_reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # RESULT BUILDERS
    # ------------------------------------------------------------------

    @classmethod
    def _success_result(
        cls,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
        position: BacktestPosition,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker="BACKTEST",
            broker_order_id=cls._uuid_as_int(
                fill.order_id,
            ),
            broker_deal_id=cls._uuid_as_int(
                fill.fill_id,
            ),
            broker_position_id=cls._uuid_as_int(
                position.position_id,
            ),
            symbol=order.symbol,
            volume=fill.volume,
            price=fill.price,
            message="Order filled.",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "position_id": str(position.position_id),
                "fill_reason": fill.reason.value,
            },
        )

    @staticmethod
    def _not_filled_result(
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            broker="BACKTEST",
            symbol=order.symbol,
            volume=order.volume,
            message=("Order was not filled: " f"{fill.reason.value}"),
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "fill_reason": fill.reason.value,
            },
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _position_side(
        side: OrderSide,
    ) -> BacktestPositionSide:
        if side == OrderSide.BUY:
            return BacktestPositionSide.LONG

        if side == OrderSide.SELL:
            return BacktestPositionSide.SHORT

        raise BacktestOrderRejectedError(f"Unsupported execution side: {side}")

    @staticmethod
    def _uuid_as_int(
        value: UUID,
    ) -> int:
        return value.int % (2**63 - 1)
