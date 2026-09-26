from __future__ import annotations

from decimal import Decimal

from app.schemas.execution import (
    ExecutionOrder,
    OrderSide as ExecutionOrderSide,
    OrderType as ExecutionOrderType,
)
from risk.models import RiskDecision
from strategies.core.signal import (
    OrderType as SignalOrderType,
    SignalDirection,
)

from .exceptions import ExecutionValidationError


class RiskDecisionMapper:
    """
    Converts an approved RiskDecision into an ExecutionOrder.

    Architectural flow:

        StrategySignal
            ↓
        RiskEngine
            ↓
        RiskDecision
            ↓
        RiskDecisionMapper
            ↓
        ExecutionOrder
            ↓
        ExecutionEngine
            ↓
        BrokerManager

    RiskDecision represents the Risk Engine's approved trading decision.

    ExecutionOrder represents the broker-agnostic instruction consumed
    by the Execution Engine and BrokerAdapter.

    This mapper is deliberately deterministic. It performs translation
    only and never changes the economic intent of an approved decision.

    This mapper does NOT:

        - calculate position size
        - recalculate risk
        - change stop loss
        - change take profit
        - generate signals
        - resolve trading-account ownership
        - query PostgreSQL
        - resolve AccountSymbol
        - communicate with a broker
        - communicate with MT5
    """

    @staticmethod
    def to_execution_order(
        decision: RiskDecision,
    ) -> ExecutionOrder:
        """
        Convert an approved RiskDecision into an ExecutionOrder.

        The RiskDecision must already have passed the Risk Engine.

        Raises:
            ExecutionValidationError:
                If the decision cannot safely be converted into an
                executable order.
        """

        if not decision.approved:
            raise ExecutionValidationError(
                "Only an approved RiskDecision can be converted "
                "into an ExecutionOrder."
            )

        account_id = decision.account_id

        if account_id is None:
            raise ExecutionValidationError(
                "Approved RiskDecision is missing account_id."
            )

        if not decision.symbol or not decision.symbol.strip():
            raise ExecutionValidationError("Approved RiskDecision is missing symbol.")

        if decision.position_size is None:
            raise ExecutionValidationError(
                "Approved RiskDecision is missing position_size."
            )

        if decision.position_size <= Decimal("0"):
            raise ExecutionValidationError(
                "Approved RiskDecision contains an invalid " "position_size."
            )

        side = RiskDecisionMapper._map_side(
            decision.direction,
        )

        order_type = RiskDecisionMapper._map_order_type(
            decision.order_type,
        )

        price = RiskDecisionMapper._resolve_price(
            decision,
            order_type,
        )

        comment = RiskDecisionMapper._build_comment(
            decision,
        )

        return ExecutionOrder(
            symbol=decision.symbol.strip(),
            account_id=account_id,
            side=side,
            order_type=order_type,
            volume=decision.position_size,
            price=price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            comment=comment,
        )

    @staticmethod
    def _map_side(
        direction: SignalDirection,
    ) -> ExecutionOrderSide:
        """
        Map strategy direction to the broker-agnostic execution side.
        """

        if direction == SignalDirection.LONG:
            return ExecutionOrderSide.BUY

        if direction == SignalDirection.SHORT:
            return ExecutionOrderSide.SELL

        raise ExecutionValidationError(f"Unsupported signal direction: {direction!r}")

    @staticmethod
    def _map_order_type(
        order_type: SignalOrderType,
    ) -> ExecutionOrderType:
        """
        Map strategy/Risk Engine order type to the execution contract.

        Explicit mapping is intentional because the strategy signal
        enums and execution enums belong to different architectural
        layers.
        """

        mapping: dict[
            SignalOrderType,
            ExecutionOrderType,
        ] = {
            SignalOrderType.MARKET: ExecutionOrderType.MARKET,
            SignalOrderType.LIMIT: ExecutionOrderType.LIMIT,
            SignalOrderType.STOP: ExecutionOrderType.STOP,
        }

        try:
            return mapping[order_type]

        except KeyError as exc:
            raise ExecutionValidationError(
                f"Unsupported order type: {order_type!r}"
            ) from exc

    @staticmethod
    def _resolve_price(
        decision: RiskDecision,
        order_type: ExecutionOrderType,
    ) -> Decimal | None:
        """
        Resolve the price required by the execution contract.

        MARKET:
            Returns None so the broker adapter can obtain a fresh
            executable market price.

        LIMIT/STOP:
            Uses the Risk Engine's approved entry_price.

        The mapper never calculates or changes the price.
        """

        if order_type == ExecutionOrderType.MARKET:
            return None

        if decision.entry_price is None:
            raise ExecutionValidationError(
                f"{order_type.value} order requires entry_price."
            )

        if decision.entry_price <= Decimal("0"):
            raise ExecutionValidationError(
                f"{order_type.value} order contains an invalid "
                f"entry_price: {decision.entry_price}."
            )

        return decision.entry_price

    @staticmethod
    def _build_comment(
        decision: RiskDecision,
    ) -> str:
        """
        Build a bounded execution comment.

        The comment is informational only. It must never be used as
        the source of account, strategy, risk, or order-routing state.
        """

        strategy_name = decision.strategy_name.strip()

        if not strategy_name:
            return "AQE"

        return f"AQE:{strategy_name}"[:255]
