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
    Convert an approved RiskDecision into an ExecutionOrder.

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
            ↓
        BrokerAdapter

    RiskDecision represents the Risk Engine's approved trading decision.

    ExecutionOrder represents the broker-agnostic execution instruction
    consumed by the Execution Engine and BrokerAdapter.

    This mapper is deliberately deterministic. It translates an approved
    decision without changing its economic intent.

    This mapper does NOT:

        - calculate position size;
        - recalculate risk;
        - change stop loss;
        - change take profit;
        - generate signals;
        - resolve trading-account ownership;
        - query PostgreSQL;
        - resolve AccountSymbol;
        - communicate with a broker;
        - communicate with MT5.
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

        symbol = str(decision.symbol).strip()

        if not symbol:
            raise ExecutionValidationError("Approved RiskDecision is missing symbol.")

        position_size = decision.position_size

        if position_size is None:
            raise ExecutionValidationError(
                "Approved RiskDecision is missing position_size."
            )

        if position_size <= Decimal("0"):
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

        stop_loss = RiskDecisionMapper._validate_optional_price(
            decision.stop_loss,
            field_name="stop_loss",
        )

        take_profit = RiskDecisionMapper._validate_optional_price(
            decision.take_profit,
            field_name="take_profit",
        )

        comment = RiskDecisionMapper._build_comment(
            decision,
        )

        return ExecutionOrder(
            symbol=symbol,
            account_id=account_id,
            side=side,
            order_type=order_type,
            volume=position_size,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    # ======================================================================
    # SIDE MAPPING
    # ======================================================================

    @staticmethod
    def _map_side(
        direction: SignalDirection,
    ) -> ExecutionOrderSide:
        """
        Map strategy direction to the broker-agnostic execution side.
        """

        if direction is SignalDirection.LONG:
            return ExecutionOrderSide.BUY

        if direction is SignalDirection.SHORT:
            return ExecutionOrderSide.SELL

        raise ExecutionValidationError(f"Unsupported signal direction: {direction!r}")

    # ======================================================================
    # ORDER TYPE MAPPING
    # ======================================================================

    @staticmethod
    def _map_order_type(
        order_type: SignalOrderType,
    ) -> ExecutionOrderType:
        """
        Map strategy/Risk Engine order type to the execution contract.

        Explicit mapping is intentional because strategy signal enums
        and execution enums belong to different architectural layers.
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

    # ======================================================================
    # PRICE RESOLUTION
    # ======================================================================

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

        if order_type is ExecutionOrderType.MARKET:
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

    # ======================================================================
    # OPTIONAL PRICE VALIDATION
    # ======================================================================

    @staticmethod
    def _validate_optional_price(
        value: Decimal | None,
        *,
        field_name: str,
    ) -> Decimal | None:
        """
        Validate an optional stop-loss or take-profit price.

        The mapper does not determine whether the level is economically
        appropriate for BUY/SELL or for a particular broker symbol.
        That belongs to the Risk Engine and broker validation layers.

        This method only prevents obviously invalid execution contracts.
        """

        if value is None:
            return None

        if value <= Decimal("0"):
            raise ExecutionValidationError(
                f"Approved RiskDecision contains an invalid " f"{field_name}: {value}."
            )

        return value

    # ======================================================================
    # COMMENT
    # ======================================================================

    @staticmethod
    def _build_comment(
        decision: RiskDecision,
    ) -> str:
        """
        Build a bounded execution comment.

        The comment is informational only.

        It must never be used as the source of:
            - account state;
            - strategy state;
            - risk state;
            - execution state;
            - order-routing state.
        """

        strategy_name = str(decision.strategy_name or "").strip()

        if not strategy_name:
            return "AQE"

        return f"AQE:{strategy_name}"[:255]


__all__ = [
    "RiskDecisionMapper",
]
