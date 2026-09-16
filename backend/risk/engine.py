"""Core AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal

from strategies.core.signal import SignalDirection

from .calculators.position_size import (
    calculate_position_risk,
    calculate_position_size,
)
from .calculators.risk_amount import calculate_risk_amount
from .enums import RiskDecisionStatus, RiskRejectionReason
from .exceptions import RiskCalculationError
from .models import RiskContext, RiskDecision
from .rules import (
    AccountRiskRule,
    DrawdownRiskRule,
    ExposureRiskRule,
    PositionRiskRule,
    RiskRule,
)


class RiskEngine:
    """Evaluate trading signals against configured risk constraints."""

    def __init__(
        self,
        rules: list[RiskRule] | None = None,
    ) -> None:
        self._rules = rules or [
            AccountRiskRule(),
            DrawdownRiskRule(),
            PositionRiskRule(),
            ExposureRiskRule(),
        ]

    @property
    def rules(self) -> tuple[RiskRule, ...]:
        """Return the configured risk rules."""
        return tuple(self._rules)

    def evaluate(self, context: RiskContext) -> RiskDecision:
        """
        Evaluate a trading signal.

        The engine first resolves the real market entry price and
        calculates the proposed position size. Policy rules then
        evaluate the complete proposed trade.
        """

        self._validate_context(context)

        signal = context.signal
        account = context.account
        config = context.config
        constraints = context.symbol_constraints

        # --------------------------------------------------------------
        # Symbol validation
        # --------------------------------------------------------------

        symbol = signal.symbol.strip().upper()

        if config.allowed_symbols is not None and symbol not in config.allowed_symbols:
            return self._reject(
                context,
                RiskRejectionReason.SYMBOL_NOT_ALLOWED,
                f"Symbol {symbol} is not allowed.",
            )

        # --------------------------------------------------------------
        # Resolve actual executable/reference entry price
        # --------------------------------------------------------------

        try:
            entry_price = context.entry_price
        except ValueError as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_SIGNAL,
                str(exc),
            )

        # --------------------------------------------------------------
        # Stop-loss validation
        # --------------------------------------------------------------

        if config.require_stop_loss and signal.stop_loss is None:
            return self._reject(
                context,
                RiskRejectionReason.STOP_LOSS_REQUIRED,
                "A stop-loss is required by the risk configuration.",
            )

        if signal.stop_loss is not None:
            if not self._validate_stop_loss(
                direction=signal.direction,
                entry_price=entry_price,
                stop_loss=signal.stop_loss,
            ):
                return self._reject(
                    context,
                    RiskRejectionReason.INVALID_STOP_LOSS,
                    "Stop-loss is invalid for the signal direction.",
                )

        # --------------------------------------------------------------
        # Take-profit validation
        # --------------------------------------------------------------

        if signal.take_profit is not None:
            if not self._validate_take_profit(
                direction=signal.direction,
                entry_price=entry_price,
                take_profit=signal.take_profit,
            ):
                return self._reject(
                    context,
                    RiskRejectionReason.INVALID_TAKE_PROFIT,
                    "Take-profit is invalid for the signal direction.",
                )

        # --------------------------------------------------------------
        # Calculate target monetary risk
        # --------------------------------------------------------------

        try:
            risk_amount = calculate_risk_amount(
                equity=account.equity,
                risk_fraction=config.risk_per_trade,
            )

            max_risk_amount = calculate_risk_amount(
                equity=account.equity,
                risk_fraction=config.max_risk_per_trade,
            )
        except (ValueError, RiskCalculationError) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_RISK_CONFIGURATION,
                str(exc),
            )

        if risk_amount > max_risk_amount:
            return self._reject(
                context,
                RiskRejectionReason.MAX_RISK_PER_TRADE,
                (
                    "Configured trade risk exceeds the maximum "
                    "risk allowed per trade."
                ),
            )

        # --------------------------------------------------------------
        # Calculate proposed position size
        # --------------------------------------------------------------

        if signal.stop_loss is None:
            return self._reject(
                context,
                RiskRejectionReason.STOP_LOSS_REQUIRED,
                "A stop-loss is required to calculate position size.",
            )

        try:
            position_size = calculate_position_size(
                equity=account.equity,
                risk_fraction=config.risk_per_trade,
                entry_price=entry_price,
                stop_loss=signal.stop_loss,
                direction=signal.direction,
                constraints=constraints,
            )
        except (ValueError, RiskCalculationError) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                str(exc),
            )

        # --------------------------------------------------------------
        # Position-size limits
        # --------------------------------------------------------------

        if position_size <= Decimal("0"):
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                "Calculated position size is below the broker minimum.",
            )

        if position_size < config.min_position_size:
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                (
                    f"Position size {position_size} is below the "
                    f"configured minimum {config.min_position_size}."
                ),
            )

        if position_size > config.max_position_size:
            position_size = self._normalize_capped_position_size(
                position_size=config.max_position_size,
                constraints=constraints,
            )

            if position_size <= Decimal("0"):
                return self._reject(
                    context,
                    RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                    "Maximum configured position size is below broker minimum.",
                )

        # --------------------------------------------------------------
        # Build context containing proposed trade size
        # --------------------------------------------------------------

        evaluation_context = context.model_copy(
            update={
                "proposed_position_size": position_size,
            }
        )

        # --------------------------------------------------------------
        # Policy rules
        # --------------------------------------------------------------

        for rule in self._rules:
            result = rule.evaluate(evaluation_context)

            if not result.passed:
                return self._reject(
                    evaluation_context,
                    result.reason,
                    result.message,
                )

        # --------------------------------------------------------------
        # Actual risk after position-size normalization
        # --------------------------------------------------------------

        try:
            actual_risk = calculate_position_risk(
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=signal.stop_loss,
                constraints=constraints,
            )
        except (ValueError, RiskCalculationError) as exc:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                str(exc),
            )

        if actual_risk <= Decimal("0"):
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Calculated position risk must be greater than zero.",
            )

        if actual_risk > max_risk_amount:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.MAX_RISK_PER_TRADE,
                (
                    "Actual position risk exceeds the configured "
                    "maximum risk per trade."
                ),
            )

        # --------------------------------------------------------------
        # Portfolio risk
        # --------------------------------------------------------------

        portfolio_risk = context.portfolio_risk + actual_risk

        max_portfolio_risk_amount = calculate_risk_amount(
            equity=account.equity,
            risk_fraction=config.max_portfolio_risk,
        )

        if portfolio_risk > max_portfolio_risk_amount:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.MAX_PORTFOLIO_RISK,
                ("The proposed trade would exceed the maximum " "portfolio risk."),
            )

        # --------------------------------------------------------------
        # Risk/reward
        # --------------------------------------------------------------

        risk_reward_ratio = self._calculate_risk_reward(
            direction=signal.direction,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        if risk_reward_ratio is not None and risk_reward_ratio < config.min_risk_reward:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_TAKE_PROFIT,
                (
                    "The trade does not meet the configured minimum "
                    f"risk/reward ratio of {config.min_risk_reward}."
                ),
            )

        # --------------------------------------------------------------
        # Approved
        # --------------------------------------------------------------

        return RiskDecision(
            status=RiskDecisionStatus.APPROVED,
            signal_id=signal.signal_id,
            account_id=account.account_id,
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            symbol=symbol,
            direction=signal.direction,
            signal_type=signal.signal_type,
            order_type=signal.order_type,
            timestamp=signal.timestamp,
            risk_amount=actual_risk,
            position_size=position_size,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_reward_ratio=risk_reward_ratio,
        )

    # ------------------------------------------------------------------
    # Context validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_context(context: RiskContext) -> None:
        """Validate the minimum context required by the engine."""

        if context.account.equity <= Decimal("0"):
            raise RiskCalculationError("Account equity must be greater than zero.")

        if not context.signal.symbol.strip():
            raise RiskCalculationError("Signal symbol cannot be empty.")

        if context.market.bid <= Decimal("0") or context.market.ask <= Decimal("0"):
            raise RiskCalculationError("Market bid and ask must be greater than zero.")

        if context.market.ask < context.market.bid:
            raise RiskCalculationError("Market ask cannot be below bid.")

    # ------------------------------------------------------------------
    # Position-size normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_capped_position_size(
        *,
        position_size: Decimal,
        constraints,
    ) -> Decimal:
        """Normalize a capped position size to broker volume rules."""

        if position_size <= Decimal("0"):
            return Decimal("0")

        step = constraints.volume_step

        if step <= Decimal("0"):
            raise RiskCalculationError("Broker volume step must be greater than zero.")

        normalized = (position_size // step) * step

        if normalized < constraints.volume_min:
            return Decimal("0")

        if normalized > constraints.volume_max:
            normalized = constraints.volume_max

        return normalized

    # ------------------------------------------------------------------
    # Stop-loss / take-profit validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_stop_loss(
        *,
        direction: SignalDirection,
        entry_price: Decimal,
        stop_loss: Decimal,
    ) -> bool:
        """Validate stop-loss relative to trade direction."""

        if direction == SignalDirection.LONG:
            return stop_loss < entry_price

        return stop_loss > entry_price

    @staticmethod
    def _validate_take_profit(
        *,
        direction: SignalDirection,
        entry_price: Decimal,
        take_profit: Decimal,
    ) -> bool:
        """Validate take-profit relative to trade direction."""

        if direction == SignalDirection.LONG:
            return take_profit > entry_price

        return take_profit < entry_price

    # ------------------------------------------------------------------
    # Risk/reward
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_risk_reward(
        *,
        direction: SignalDirection,
        entry_price: Decimal,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> Decimal | None:
        """Calculate the trade risk/reward ratio."""

        if stop_loss is None or take_profit is None:
            return None

        if direction == SignalDirection.LONG:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit

        if risk <= Decimal("0"):
            return None

        if reward <= Decimal("0"):
            return Decimal("0")

        return reward / risk

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    @staticmethod
    def _reject(
        context: RiskContext,
        reason: RiskRejectionReason | None,
        message: str | None,
    ) -> RiskDecision:
        """Build a rejected RiskDecision."""

        if reason is None:
            reason = RiskRejectionReason.INVALID_SIGNAL

        signal = context.signal

        return RiskDecision(
            status=RiskDecisionStatus.REJECTED,
            signal_id=signal.signal_id,
            account_id=context.account.account_id,
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            symbol=signal.symbol.strip().upper(),
            direction=signal.direction,
            signal_type=signal.signal_type,
            order_type=signal.order_type,
            timestamp=signal.timestamp,
            rejection_reason=reason,
            message=message,
        )
