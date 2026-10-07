"""Simulated execution engine for AQE backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
)

from .fill import BacktestFill, BacktestFillEngine
from .market import BacktestCandle, BacktestMarket
from .portfolio import BacktestPortfolio
from .position import BacktestPosition, BacktestPositionSide

# ======================================================================
# ERRORS
# ======================================================================


class BacktestExecutionError(Exception):
    """Base exception for backtest execution failures."""


class BacktestOrderRejectedError(BacktestExecutionError):
    """Raised when a backtest order cannot be executed."""


# ======================================================================
# EXECUTION CONTEXT
# ======================================================================


@dataclass(frozen=True, slots=True)
class BacktestExecutionContext:
    """
    Strategy attribution and execution metadata associated with an order.

    Strategy identity intentionally remains outside ExecutionOrder because
    ExecutionOrder is an execution/broker contract while attribution belongs
    to the backtest runtime.
    """

    strategy_id: str | None = None
    strategy_name: str | None = None
    magic_number: int = 10001


# ======================================================================
# EXECUTION ENGINE
# ======================================================================


class BacktestExecution:
    """
    Apply simulated fills to the shared backtest portfolio.

    Responsibilities:

        ExecutionOrder
              ↓
        BacktestFillEngine
              ↓
        BacktestFill
              ↓
        BacktestPosition
              ↓
        BacktestPortfolio

    Margin responsibilities:

        BacktestConfig.leverage
              ↓
        margin_rate = 1 / leverage
              ↓
        BacktestExecution
              ↓
        required margin =
            volume × fill_price × contract_size × margin_rate
              ↓
        BacktestPortfolio.reserve_margin()

    This component intentionally does not:

        - generate strategy signals
        - evaluate risk
        - load historical market data
        - own the simulation clock
        - manage pending-order lifetime
        - communicate with MT5
        - communicate with Redis
        - communicate with PostgreSQL

    BacktestEngine owns historical event sequencing and pending orders.

    BacktestExecution owns fill application and position state changes.
    """

    BROKER_NAME = "BACKTEST"

    def __init__(
        self,
        portfolio: BacktestPortfolio,
        fill_engine: BacktestFillEngine,
        margin_rate: Decimal,
    ) -> None:
        if portfolio is None:
            raise TypeError("portfolio is required.")

        if fill_engine is None:
            raise TypeError("fill_engine is required.")

        if not isinstance(margin_rate, Decimal):
            try:
                margin_rate = Decimal(str(margin_rate))
            except Exception as exc:
                raise ValueError("margin_rate must be a valid Decimal.") from exc

        if not margin_rate.is_finite():
            raise ValueError("margin_rate must be finite.")

        if margin_rate <= Decimal("0"):
            raise ValueError("margin_rate must be greater than zero.")

        self.portfolio = portfolio
        self.fill_engine = fill_engine
        self.margin_rate = margin_rate

    # ==================================================================
    # MARKET ORDER EXECUTION
    # ==================================================================

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
        Execute an immediately executable MARKET order.

        LIMIT and STOP orders belong to the pending-order subsystem and
        are therefore rejected here. Once a pending order is triggered,
        ``apply_pending_fill()`` is used.
        """
        self._validate_order(order)
        self._validate_market(market)
        self._validate_contract_size(contract_size)
        self._validate_account(order)

        self._validate_order_symbol_against_market(
            order=order,
            market=market,
        )

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise BacktestOrderRejectedError(
                "LIMIT and STOP orders must be submitted to the "
                "backtest pending-order subsystem."
            )

        if order.order_type != OrderType.MARKET:
            raise BacktestOrderRejectedError(
                f"Unsupported execution order type: {order.order_type}"
            )

        resolved_order_id = order_id or uuid4()

        try:
            fill = self.fill_engine.execute(
                order=order,
                market=market,
                order_id=resolved_order_id,
            )
        except BacktestExecutionError:
            raise
        except Exception as exc:
            raise BacktestExecutionError(
                "Backtest fill generation failed: " f"{type(exc).__name__}: {exc}"
            ) from exc

        if not fill.filled:
            return self._not_filled_result(
                order=order,
                fill=fill,
            )

        position = self.apply_fill(
            order=order,
            fill=fill,
            context=context,
            contract_size=contract_size,
        )

        return self._success_result(
            order=order,
            fill=fill,
            position=position,
            context=context,
        )

    # ==================================================================
    # APPLY FILLED ORDER
    # ==================================================================

    def apply_fill(
        self,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
        context: BacktestExecutionContext | None = None,
        contract_size: Decimal = Decimal("1"),
    ) -> BacktestPosition:
        """
        Apply an already-generated fill to the shared portfolio.

        The fill engine is deliberately not called from this method.

        This method is used for:

        - normal MARKET execution after fill generation
        - triggered LIMIT orders
        - triggered STOP orders

        Entry commission is recorded directly when the position is
        created.

        Required margin is calculated from the actual fill price and
        the resolved contract size, then reserved against the shared
        portfolio.

        The position model is responsible for accumulating the later
        exit commission when the position is closed.
        """
        self._validate_order(order)

        if fill is None:
            raise BacktestExecutionError("BacktestFill is required.")

        if not fill.filled:
            raise BacktestExecutionError("Cannot apply a fill that is not FILLED.")

        self._validate_account(order)
        self._validate_contract_size(contract_size)

        normalized_order_symbol = self._normalize_symbol(
            order.symbol,
        )

        normalized_fill_symbol = self._normalize_symbol(
            fill.symbol,
        )

        if normalized_order_symbol != normalized_fill_symbol:
            raise BacktestExecutionError("Fill symbol does not match order symbol.")

        if fill.volume != order.volume:
            raise BacktestExecutionError("Fill volume does not match order volume.")

        if fill.volume <= Decimal("0"):
            raise BacktestExecutionError("Filled volume must be greater than zero.")

        if fill.price <= Decimal("0"):
            raise BacktestExecutionError("Filled price must be greater than zero.")

        entry_commission = self._non_negative_decimal(
            fill.commission,
            "Entry commission",
        )

        strategy_id = self._resolve_strategy_id(
            context,
        )

        strategy_name = self._resolve_strategy_name(
            context,
        )

        position = BacktestPosition.open(
            account_id=self.portfolio.account_id,
            symbol=normalized_order_symbol,
            side=self._position_side(order.side),
            volume=fill.volume,
            entry_price=fill.price,
            opened_at=fill.timestamp,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            entry_commission=entry_commission,
        )

        # --------------------------------------------------------------
        # Margin reservation
        #
        # required margin is based on the actual filled position:
        #
        #     notional =
        #         volume × fill_price × contract_size
        #
        #     margin =
        #         notional × margin_rate
        # --------------------------------------------------------------

        required_margin = self.calculate_required_margin(
            volume=fill.volume,
            price=fill.price,
            contract_size=contract_size,
        )

        try:
            self.portfolio.add_position(
                position,
                reserved_margin=required_margin,
            )
        except BacktestExecutionError:
            raise
        except Exception as exc:
            raise BacktestExecutionError(
                "Failed to register filled position in the "
                "backtest portfolio: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        return position

    # ==================================================================
    # MARGIN
    # ==================================================================

    def calculate_required_margin(
        self,
        *,
        volume: Decimal,
        price: Decimal,
        contract_size: Decimal,
    ) -> Decimal:
        """
        Calculate the margin required for a filled position.

        Formula:

            notional exposure =
                volume × price × contract_size

            required margin =
                notional exposure × margin_rate

        ``margin_rate`` is resolved from account leverage by the
        BacktestEngine:

            margin_rate = 1 / leverage
        """

        if volume <= Decimal("0"):
            raise BacktestExecutionError(
                "Volume must be greater than zero for margin calculation."
            )

        if price <= Decimal("0"):
            raise BacktestExecutionError(
                "Price must be greater than zero for margin calculation."
            )

        self._validate_contract_size(
            contract_size,
        )

        notional = volume * price * contract_size

        required_margin = notional * self.margin_rate

        if not required_margin.is_finite():
            raise BacktestExecutionError("Calculated required margin must be finite.")

        if required_margin <= Decimal("0"):
            raise BacktestExecutionError(
                "Calculated required margin must be greater than zero."
            )

        return required_margin

    # ==================================================================
    # PENDING ORDER FILLS
    # ==================================================================

    def apply_pending_fill(
        self,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
        context: BacktestExecutionContext | None = None,
        contract_size: Decimal = Decimal("1"),
    ) -> ExecutionResult:
        """
        Apply a fill generated for a pending LIMIT or STOP order.

        BacktestEngine owns the pending-order lifecycle. This method only
        applies the already-generated fill to portfolio state.

        Contract size is passed explicitly because pending orders may
        involve instruments such as XAUUSD/XAUAUD whose contract size
        is not one.
        """
        self._validate_order(order)
        self._validate_contract_size(contract_size)

        if order.order_type not in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            raise BacktestOrderRejectedError(
                "apply_pending_fill() requires a LIMIT or STOP order."
            )

        if fill is None:
            raise BacktestExecutionError("BacktestFill is required.")

        if not fill.filled:
            return self._not_filled_result(
                order=order,
                fill=fill,
            )

        position = self.apply_fill(
            order=order,
            fill=fill,
            context=context,
            contract_size=contract_size,
        )

        return self._success_result(
            order=order,
            fill=fill,
            position=position,
            context=context,
        )

    # ==================================================================
    # POSITION CLOSING
    # ==================================================================

    def close_position(
        self,
        *,
        position_id: UUID,
        market: BacktestMarket,
        exit_reason: str = "MANUAL",
        contract_size: Decimal = Decimal("1"),
    ) -> ExecutionResult:
        """
        Close an existing position using simulated market execution.

        The position's original strategy attribution is preserved in the
        returned execution result.

        Commission convention:

            position.commission
                = entry commission + exit commission

        Therefore only the exit commission is passed to
        ``portfolio.close_position()``.

        ``BacktestPortfolio.close_position()`` releases any margin that
        was reserved for the position.
        """
        if not isinstance(position_id, UUID):
            raise BacktestExecutionError("position_id must be a UUID.")

        self._validate_market(
            market,
        )

        self._validate_contract_size(
            contract_size,
        )

        position = self.portfolio.get_position(
            position_id,
        )

        if position is None:
            raise BacktestExecutionError(f"Position '{position_id}' does not exist.")

        if not position.is_open:
            raise BacktestExecutionError(f"Position '{position_id}' is already closed.")

        if self._normalize_symbol(position.symbol) != self._normalize_symbol(
            market.symbol
        ):
            raise BacktestExecutionError(
                "Position symbol does not match market symbol."
            )

        exit_reason_normalized = self._normalize_exit_reason(
            exit_reason,
        )

        exit_side = (
            OrderSide.SELL
            if position.side == BacktestPositionSide.LONG
            else OrderSide.BUY
        )

        order = ExecutionOrder(
            symbol=position.symbol,
            account_id=position.account_id,
            side=exit_side,
            order_type=OrderType.MARKET,
            volume=position.volume,
        )

        try:
            fill = self.fill_engine.execute(
                order=order,
                market=market,
            )
        except BacktestExecutionError:
            raise
        except Exception as exc:
            raise BacktestExecutionError(
                "Backtest position-close fill generation failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not fill.filled:
            return self._not_filled_result(
                order=order,
                fill=fill,
            )

        entry_commission = self._non_negative_decimal(
            position.commission,
            "Entry commission",
        )

        exit_commission = self._non_negative_decimal(
            fill.commission,
            "Exit commission",
        )

        self.portfolio.close_position(
            position_id=position_id,
            exit_price=fill.price,
            closed_at=fill.timestamp,
            commission=exit_commission,
            swap=Decimal("0"),
            exit_reason=exit_reason_normalized,
            contract_size=contract_size,
        )

        total_commission = entry_commission + exit_commission

        return self._close_success_result(
            position=position,
            fill=fill,
            exit_reason=exit_reason_normalized,
            entry_commission=entry_commission,
            exit_commission=exit_commission,
            total_commission=total_commission,
        )

    # ==================================================================
    # STOP LOSS / TAKE PROFIT
    # ==================================================================

    def check_position_exits(
        self,
        *,
        market: BacktestMarket,
        contract_sizes: dict[str, Decimal] | None = None,
    ) -> list[ExecutionResult]:
        """
        Check every open position on the current symbol for SL/TP triggers.

        For OHLC-only data, exact intrabar ordering is unknowable.

        Conservative rule:

            STOP LOSS takes precedence over TAKE PROFIT

        when both levels are touched within the same candle.
        """
        self._validate_market(
            market,
        )

        normalized_contract_sizes: dict[str, Decimal] = {}

        for symbol, value in (contract_sizes or {}).items():
            normalized_symbol = self._normalize_symbol(
                symbol,
            )

            self._validate_contract_size(
                value,
            )

            normalized_contract_sizes[normalized_symbol] = value

        results: list[ExecutionResult] = []

        for position in tuple(self.portfolio.open_positions):
            if not position.is_open:
                continue

            if self._normalize_symbol(position.symbol) != self._normalize_symbol(
                market.symbol
            ):
                continue

            trigger = self._resolve_exit_trigger(
                position=position,
                candle=market.candle,
            )

            if trigger is None:
                continue

            exit_price, reason = trigger

            contract_size = normalized_contract_sizes.get(
                self._normalize_symbol(position.symbol),
                Decimal("1"),
            )

            results.append(
                self._close_position_at_trigger(
                    position=position,
                    exit_price=exit_price,
                    timestamp=market.candle.timestamp,
                    reason=reason,
                    contract_size=contract_size,
                )
            )

        return results

    def _resolve_exit_trigger(
        self,
        *,
        position: BacktestPosition,
        candle: BacktestCandle,
    ) -> tuple[Decimal, str] | None:
        """
        Determine whether SL or TP was touched by the current candle.

        When both levels are touched during the same candle, STOP LOSS
        takes precedence because OHLC data cannot establish the true
        intrabar sequence.
        """
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

            return None

        if position.side == BacktestPositionSide.SHORT:
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

        raise BacktestExecutionError(f"Unsupported position side: {position.side}")

    def _close_position_at_trigger(
        self,
        *,
        position: BacktestPosition,
        exit_price: Decimal,
        timestamp: datetime,
        reason: str,
        contract_size: Decimal,
    ) -> ExecutionResult:
        """
        Close a position at a previously resolved SL/TP trigger price.

        No second fill is generated here because the candle itself already
        determined the trigger price.

        Only the exit commission is passed to the portfolio. The position
        already contains its entry commission.

        The portfolio releases the position's reserved margin as part of
        the close operation.
        """
        self._validate_contract_size(
            contract_size,
        )

        if exit_price <= Decimal("0"):
            raise BacktestExecutionError("Exit price must be greater than zero.")

        if not isinstance(timestamp, datetime):
            raise BacktestExecutionError("Exit timestamp must be a datetime.")

        if not position.is_open:
            raise BacktestExecutionError(
                f"Position '{position.position_id}' is already closed."
            )

        normalized_reason = self._normalize_exit_reason(
            reason,
        )

        entry_commission = self._non_negative_decimal(
            position.commission,
            "Entry commission",
        )

        exit_commission = self._non_negative_decimal(
            position.volume * self.fill_engine.config.commission_per_volume,
            "Exit commission",
        )

        self.portfolio.close_position(
            position_id=position.position_id,
            exit_price=exit_price,
            closed_at=timestamp,
            commission=exit_commission,
            swap=Decimal("0"),
            exit_reason=normalized_reason,
            contract_size=contract_size,
        )

        total_commission = entry_commission + exit_commission
        deal_id = uuid4()

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker=self.BROKER_NAME,
            broker_order_id=self._uuid_as_int(
                position.position_id,
            ),
            broker_deal_id=self._uuid_as_int(
                deal_id,
            ),
            broker_position_id=self._uuid_as_int(
                position.position_id,
            ),
            symbol=self._normalize_symbol(
                position.symbol,
            ),
            volume=position.volume,
            price=exit_price,
            message=f"Position closed by {normalized_reason}.",
            raw_response={
                "position_id": str(position.position_id),
                "deal_id": str(deal_id),
                "exit_reason": normalized_reason,
                "exit_price": str(exit_price),
                "entry_commission": str(entry_commission),
                "exit_commission": str(exit_commission),
                "total_commission": str(total_commission),
                "commission": str(total_commission),
                "strategy_id": position.strategy_id,
                "strategy_name": position.strategy_name,
            },
        )

    # ==================================================================
    # RESULT BUILDERS
    # ==================================================================

    @classmethod
    def _success_result(
        cls,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
        position: BacktestPosition,
        context: BacktestExecutionContext | None = None,
    ) -> ExecutionResult:
        """Build the execution result for a newly opened position."""
        strategy_id = (
            cls._normalize_strategy_value(
                context.strategy_id,
            )
            if context is not None
            else position.strategy_id
        )

        strategy_name = (
            cls._normalize_strategy_value(
                context.strategy_name,
            )
            if context is not None
            else position.strategy_name
        )

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker=cls.BROKER_NAME,
            broker_order_id=cls._uuid_as_int(
                fill.order_id,
            ),
            broker_deal_id=cls._uuid_as_int(
                fill.fill_id,
            ),
            broker_position_id=cls._uuid_as_int(
                position.position_id,
            ),
            symbol=cls._normalize_symbol(
                order.symbol,
            ),
            volume=fill.volume,
            price=fill.price,
            message="Order filled.",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "position_id": str(position.position_id),
                "fill_reason": fill.reason.value,
                "commission": str(fill.commission),
                "slippage": str(fill.slippage),
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
            },
        )

    @classmethod
    def _close_success_result(
        cls,
        *,
        position: BacktestPosition,
        fill: BacktestFill,
        exit_reason: str,
        entry_commission: Decimal,
        exit_commission: Decimal,
        total_commission: Decimal,
    ) -> ExecutionResult:
        """Build the execution result for a manual position close."""
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            broker=cls.BROKER_NAME,
            broker_order_id=cls._uuid_as_int(
                fill.order_id,
            ),
            broker_deal_id=cls._uuid_as_int(
                fill.fill_id,
            ),
            broker_position_id=cls._uuid_as_int(
                position.position_id,
            ),
            symbol=cls._normalize_symbol(
                position.symbol,
            ),
            volume=position.volume,
            price=fill.price,
            message=f"Position closed: {exit_reason}.",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "position_id": str(position.position_id),
                "exit_reason": exit_reason,
                "entry_commission": str(entry_commission),
                "exit_commission": str(exit_commission),
                "total_commission": str(total_commission),
                "commission": str(total_commission),
                "slippage": str(fill.slippage),
                "strategy_id": position.strategy_id,
                "strategy_name": position.strategy_name,
            },
        )

    @classmethod
    def _not_filled_result(
        cls,
        *,
        order: ExecutionOrder,
        fill: BacktestFill,
    ) -> ExecutionResult:
        """Build an execution result for a fill that did not occur."""
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            broker=cls.BROKER_NAME,
            symbol=cls._normalize_symbol(
                order.symbol,
            ),
            volume=order.volume,
            price=None,
            message=f"Order was not filled: {fill.reason.value}",
            raw_response={
                "fill_id": str(fill.fill_id),
                "order_id": str(fill.order_id),
                "fill_reason": fill.reason.value,
                "status": fill.status.value,
            },
        )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_order(
        order: ExecutionOrder,
    ) -> None:
        if order is None:
            raise BacktestOrderRejectedError("ExecutionOrder is required.")

        if not isinstance(
            order,
            ExecutionOrder,
        ):
            raise BacktestOrderRejectedError(
                "order must be an ExecutionOrder instance."
            )

        if not isinstance(
            order.account_id,
            UUID,
        ):
            raise BacktestOrderRejectedError(
                "ExecutionOrder must contain an account_id."
            )

        if order.volume <= Decimal("0"):
            raise BacktestOrderRejectedError("Order volume must be greater than zero.")

        BacktestExecution._normalize_symbol(
            order.symbol,
        )

        if order.order_type in {
            OrderType.LIMIT,
            OrderType.STOP,
        }:
            if order.price is None:
                raise BacktestOrderRejectedError(
                    f"{order.order_type.value} order requires a price."
                )

            if order.price <= Decimal("0"):
                raise BacktestOrderRejectedError(
                    f"{order.order_type.value} order price must be "
                    "greater than zero."
                )

        if order.price is not None and order.price <= Decimal("0"):
            raise BacktestOrderRejectedError(
                "Order price must be greater than zero when provided."
            )

        if order.stop_loss is not None and order.stop_loss <= Decimal("0"):
            raise BacktestOrderRejectedError(
                "Stop-loss price must be greater than zero."
            )

        if order.take_profit is not None and order.take_profit <= Decimal("0"):
            raise BacktestOrderRejectedError(
                "Take-profit price must be greater than zero."
            )

    def _validate_account(
        self,
        order: ExecutionOrder,
    ) -> None:
        if order.account_id != self.portfolio.account_id:
            raise BacktestOrderRejectedError(
                "Order account does not match the backtest portfolio."
            )

    @staticmethod
    def _validate_market(
        market: BacktestMarket,
    ) -> None:
        if market is None:
            raise BacktestExecutionError("BacktestMarket is required.")

        if not isinstance(
            market,
            BacktestMarket,
        ):
            raise BacktestExecutionError("market must be a BacktestMarket instance.")

        BacktestExecution._normalize_symbol(
            market.symbol,
        )

    @staticmethod
    def _validate_contract_size(
        contract_size: Decimal,
    ) -> None:
        if not isinstance(
            contract_size,
            Decimal,
        ):
            raise BacktestExecutionError("Contract size must be a Decimal.")

        if not contract_size.is_finite():
            raise BacktestExecutionError("Contract size must be finite.")

        if contract_size <= Decimal("0"):
            raise BacktestExecutionError("Contract size must be greater than zero.")

    @staticmethod
    def _validate_order_symbol_against_market(
        *,
        order: ExecutionOrder,
        market: BacktestMarket,
    ) -> None:
        if BacktestExecution._normalize_symbol(
            order.symbol,
        ) != BacktestExecution._normalize_symbol(
            market.symbol,
        ):
            raise BacktestOrderRejectedError(
                "Order symbol does not match the current market symbol."
            )

    # ==================================================================
    # HELPERS
    # ==================================================================

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
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        if not isinstance(
            symbol,
            str,
        ):
            raise BacktestExecutionError("Symbol must be a string.")

        normalized = symbol.strip().upper()

        if not normalized:
            raise BacktestExecutionError("Symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_strategy_value(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @staticmethod
    def _resolve_strategy_id(
        context: BacktestExecutionContext | None,
    ) -> str | None:
        if context is None:
            return None

        return BacktestExecution._normalize_strategy_value(
            context.strategy_id,
        )

    @staticmethod
    def _resolve_strategy_name(
        context: BacktestExecutionContext | None,
    ) -> str | None:
        if context is None:
            return None

        return BacktestExecution._normalize_strategy_value(
            context.strategy_name,
        )

    @staticmethod
    def _normalize_exit_reason(
        reason: str,
    ) -> str:
        if not isinstance(
            reason,
            str,
        ):
            raise BacktestExecutionError("Exit reason must be a string.")

        normalized = reason.strip().upper()

        if not normalized:
            raise BacktestExecutionError("Exit reason cannot be empty.")

        return normalized

    @staticmethod
    def _non_negative_decimal(
        value: Decimal,
        field_name: str,
    ) -> Decimal:
        """
        Normalize a non-negative monetary value.

        Transaction costs are represented as positive magnitudes.
        """
        if not isinstance(
            value,
            Decimal,
        ):
            try:
                value = Decimal(
                    str(value),
                )
            except Exception as exc:
                raise BacktestExecutionError(
                    f"{field_name} must be a valid Decimal."
                ) from exc

        if not value.is_finite():
            raise BacktestExecutionError(f"{field_name} must be finite.")

        if value < Decimal("0"):
            raise BacktestExecutionError(f"{field_name} cannot be negative.")

        return value

    @staticmethod
    def _uuid_as_int(
        value: UUID,
    ) -> int:
        """
        Convert an AQE UUID into the positive integer domain exposed by
        the broker abstraction.

        The zero value is avoided because broker ticket/order IDs are
        expected to be positive identifiers.
        """
        if not isinstance(
            value,
            UUID,
        ):
            raise BacktestExecutionError("Broker identifier source must be a UUID.")

        return value.int % (2**63 - 1) or 1
