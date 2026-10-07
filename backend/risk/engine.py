"""Core AQE Risk Engine."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Any

from strategies.core.signal import SignalDirection

from .calculators.exposure import (
    calculate_position_risk_exposure,
    calculate_symbol_exposure,
    calculate_total_exposure,
)
from .calculators.position_size import (
    calculate_position_risk,
    calculate_position_size,
)
from .calculators.risk_amount import calculate_risk_amount
from .enums import RiskDecisionStatus, RiskRejectionReason
from .exceptions import RiskCalculationError
from .models import RiskContext, RiskDecision, SymbolRiskConstraints
from .rules import (
    AccountRiskRule,
    DrawdownRiskRule,
    ExposureRiskRule,
    MarginRiskRule,
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
            MarginRiskRule(),
            ExposureRiskRule(),
        ]

    @property
    def rules(self) -> tuple[RiskRule, ...]:
        """Return the configured risk rules."""

        return tuple(self._rules)

    def evaluate(self, context: RiskContext) -> RiskDecision:
        """
        Evaluate a trading signal.

        The strategy layer may provide numeric price values as floats.
        The Risk Engine establishes the Decimal boundary before performing
        any monetary or price arithmetic.

        The engine:

        1. validates the signal and market context;
        2. calculates the target monetary risk;
        3. calculates a stop-loss-based position size;
        4. applies broker and configured position-size limits;
        5. constrains that size against portfolio, symbol, and strategy
           exposure limits;
        6. evaluates the resulting trade against the configured risk rules;
        7. calculates actual monetary risk from the final position size;
        8. validates portfolio risk and risk/reward;
        9. returns an auditable RiskDecision.

        Exposure constraints act as position-size ceilings. This means the
        risk engine can reduce an oversized risk-based position to the
        largest size permitted by the configured exposure policy rather than
        rejecting the trade solely because its initial risk-based size was
        too large.

        The ExposureRiskRule remains active as a final safety check after
        exposure-constrained sizing.

        Strategy metadata is preserved unchanged in the resulting
        RiskDecision and augmented with ``risk_engine_diagnostics``.
        """

        self._validate_context(context)

        signal = context.signal
        account = context.account
        config = context.config
        constraints = context.symbol_constraints

        # --------------------------------------------------------------
        # Normalize numeric signal values at the Risk Engine boundary
        # --------------------------------------------------------------

        normalized_stop_loss = (
            self._decimal(signal.stop_loss) if signal.stop_loss is not None else None
        )

        normalized_take_profit = (
            self._decimal(signal.take_profit)
            if signal.take_profit is not None
            else None
        )

        # --------------------------------------------------------------
        # Symbol validation
        # --------------------------------------------------------------

        symbol = signal.symbol.strip().upper()

        if config.allowed_symbols is not None and symbol not in config.allowed_symbols:
            return self._reject(
                context,
                RiskRejectionReason.SYMBOL_NOT_ALLOWED,
                f"Symbol {symbol} is not allowed.",
                entry_price=self._safe_decimal(context.entry_price),
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Resolve actual executable/reference entry price
        # --------------------------------------------------------------

        try:
            entry_price = self._decimal(context.entry_price)

        except (TypeError, ValueError, ArithmeticError) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_SIGNAL,
                f"Invalid entry price: {exc}",
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Stop-loss validation
        # --------------------------------------------------------------

        if config.require_stop_loss and normalized_stop_loss is None:
            return self._reject(
                context,
                RiskRejectionReason.STOP_LOSS_REQUIRED,
                "A stop-loss is required by the risk configuration.",
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if normalized_stop_loss is not None:
            if not self._validate_stop_loss(
                direction=signal.direction,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
            ):
                return self._reject(
                    context,
                    RiskRejectionReason.INVALID_STOP_LOSS,
                    "Stop-loss is invalid for the signal direction.",
                    entry_price=entry_price,
                    stop_loss=normalized_stop_loss,
                    take_profit=normalized_take_profit,
                )

        # --------------------------------------------------------------
        # Take-profit validation
        # --------------------------------------------------------------

        if normalized_take_profit is not None:
            if not self._validate_take_profit(
                direction=signal.direction,
                entry_price=entry_price,
                take_profit=normalized_take_profit,
            ):
                return self._reject(
                    context,
                    RiskRejectionReason.INVALID_TAKE_PROFIT,
                    "Take-profit is invalid for the signal direction.",
                    entry_price=entry_price,
                    stop_loss=normalized_stop_loss,
                    take_profit=normalized_take_profit,
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

        except (
            ValueError,
            RiskCalculationError,
        ) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_RISK_CONFIGURATION,
                str(exc),
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if risk_amount > max_risk_amount:
            return self._reject(
                context,
                RiskRejectionReason.MAX_RISK_PER_TRADE,
                "Configured trade risk exceeds the maximum risk allowed per trade.",
                risk_amount=risk_amount,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Calculate proposed position size
        # --------------------------------------------------------------

        if normalized_stop_loss is None:
            return self._reject(
                context,
                RiskRejectionReason.STOP_LOSS_REQUIRED,
                "A stop-loss is required to calculate position size.",
                risk_amount=risk_amount,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        try:
            position_size = calculate_position_size(
                risk_amount=risk_amount,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                constraints=constraints,
            )

        except (
            ValueError,
            RiskCalculationError,
        ) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                str(exc),
                risk_amount=risk_amount,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        initial_position_size = position_size

        # --------------------------------------------------------------
        # Position-size limits
        # --------------------------------------------------------------

        if position_size <= Decimal("0"):
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                "Calculated position size is below the broker minimum.",
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if position_size < config.min_position_size:
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                (
                    f"Position size {position_size} is below the "
                    f"configured minimum {config.min_position_size}."
                ),
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
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
                    risk_amount=risk_amount,
                    position_size=position_size,
                    entry_price=entry_price,
                    stop_loss=normalized_stop_loss,
                    take_profit=normalized_take_profit,
                )

        position_size_after_config_caps = position_size

        # --------------------------------------------------------------
        # Exposure-constrained sizing
        #
        # Exposure limits are expressed as multiples of equity and are
        # based on absolute notional exposure:
        #
        #     quantity × entry_price × contract_size
        #
        # The maximum allowable new position is the most restrictive of:
        #
        #     portfolio exposure remaining
        #     symbol exposure remaining
        #     strategy exposure remaining
        #
        # Existing exposure is calculated using each existing position's
        # own symbol constraints.
        # --------------------------------------------------------------

        try:
            position_size = self._apply_exposure_position_size_caps(
                context=context,
                entry_price=entry_price,
                position_size=position_size,
            )

        except (
            ValueError,
            RiskCalculationError,
        ) as exc:
            return self._reject(
                context,
                RiskRejectionReason.INVALID_RISK_CONFIGURATION,
                str(exc),
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if position_size <= Decimal("0"):
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                (
                    "Portfolio, symbol, and strategy exposure limits "
                    "constrain the position below the broker minimum."
                ),
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if position_size < config.min_position_size:
            return self._reject(
                context,
                RiskRejectionReason.POSITION_SIZE_TOO_SMALL,
                (
                    "Portfolio, symbol, and strategy exposure limits "
                    f"constrain the position below the configured minimum "
                    f"{config.min_position_size}."
                ),
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Build context containing the fully constrained proposed trade
        # --------------------------------------------------------------

        evaluation_context = context.model_copy(
            update={
                # The original context.entry_price may be a float because
                # strategy signals can originate with float price values.
                # Every downstream risk rule must receive the normalized
                # Decimal value so monetary arithmetic never performs
                # Decimal × float operations.
                "entry_price": entry_price,
                "proposed_position_size": position_size,
            },
        )

        # --------------------------------------------------------------
        # Policy rules
        # --------------------------------------------------------------

        for rule in self._rules:
            result = rule.evaluate(
                evaluation_context,
            )

            if not result.passed:
                return self._reject(
                    evaluation_context,
                    result.reason,
                    result.message,
                    risk_amount=risk_amount,
                    position_size=position_size,
                    entry_price=entry_price,
                    stop_loss=normalized_stop_loss,
                    take_profit=normalized_take_profit,
                    risk_reward_ratio=self._calculate_risk_reward(
                        direction=signal.direction,
                        entry_price=entry_price,
                        stop_loss=normalized_stop_loss,
                        take_profit=normalized_take_profit,
                    ),
                )

        # --------------------------------------------------------------
        # Actual risk after all position-size normalization
        # --------------------------------------------------------------

        try:
            actual_risk = calculate_position_risk(
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                constraints=constraints,
            )

        except (
            ValueError,
            RiskCalculationError,
        ) as exc:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                str(exc),
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if actual_risk <= Decimal("0"):
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Calculated position risk must be greater than zero.",
                risk_amount=risk_amount,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        if actual_risk > max_risk_amount:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.MAX_RISK_PER_TRADE,
                "Actual position risk exceeds the configured maximum risk per trade.",
                risk_amount=actual_risk,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Portfolio risk
        # --------------------------------------------------------------

        portfolio_risk_before = context.portfolio_risk

        portfolio_risk = portfolio_risk_before + actual_risk

        max_portfolio_risk_amount = calculate_risk_amount(
            equity=account.equity,
            risk_fraction=config.max_portfolio_risk,
        )

        if portfolio_risk > max_portfolio_risk_amount:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.MAX_PORTFOLIO_RISK,
                "The proposed trade would exceed the maximum portfolio risk.",
                risk_amount=actual_risk,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
            )

        # --------------------------------------------------------------
        # Risk/reward
        # --------------------------------------------------------------

        risk_reward_ratio = self._calculate_risk_reward(
            direction=signal.direction,
            entry_price=entry_price,
            stop_loss=normalized_stop_loss,
            take_profit=normalized_take_profit,
        )

        if risk_reward_ratio is not None and risk_reward_ratio < config.min_risk_reward:
            return self._reject(
                evaluation_context,
                RiskRejectionReason.INVALID_TAKE_PROFIT,
                (
                    "The trade does not meet the configured minimum "
                    f"risk/reward ratio of {config.min_risk_reward}."
                ),
                risk_amount=actual_risk,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=normalized_stop_loss,
                take_profit=normalized_take_profit,
                risk_reward_ratio=risk_reward_ratio,
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
            stop_loss=normalized_stop_loss,
            take_profit=normalized_take_profit,
            risk_reward_ratio=risk_reward_ratio,
            metadata=self._build_decision_metadata(
                context,
                target_risk_amount=risk_amount,
                max_risk_amount=max_risk_amount,
                initial_position_size=initial_position_size,
                position_size_after_config_caps=position_size_after_config_caps,
                final_position_size=position_size,
                actual_risk=actual_risk,
                portfolio_risk_before=portfolio_risk_before,
                portfolio_risk_after=portfolio_risk,
                max_portfolio_risk_amount=max_portfolio_risk_amount,
            ),
        )

    # ------------------------------------------------------------------
    # Exposure-constrained sizing
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_exposure_position_size_caps(
        *,
        context: RiskContext,
        entry_price: Decimal,
        position_size: Decimal,
    ) -> Decimal:
        """
        Reduce position size so the proposed trade remains within all
        configured notional exposure limits.

        Exposure is calculated as:

            quantity × price × contract_size

        The most restrictive remaining capacity across portfolio, symbol,
        and strategy exposure becomes the maximum permissible position size.
        """

        if position_size <= Decimal("0"):
            return Decimal("0")

        account = context.account
        config = context.config
        signal = context.signal
        constraints = context.symbol_constraints

        contract_size = constraints.contract_size

        if contract_size <= Decimal("0"):
            raise RiskCalculationError(
                "Contract size must be greater than zero for exposure sizing.",
            )

        if entry_price <= Decimal("0"):
            raise RiskCalculationError(
                "Entry price must be greater than zero for exposure sizing.",
            )

        exposure_per_unit = entry_price * contract_size

        if exposure_per_unit <= Decimal("0"):
            raise RiskCalculationError(
                "Exposure per unit must be greater than zero.",
            )

        normalized_symbol = signal.symbol.strip().upper()

        # --------------------------------------------------------------
        # Existing portfolio exposure
        # --------------------------------------------------------------

        current_portfolio_exposure = calculate_total_exposure(
            context.positions,
            context.constraints_by_symbol,
        )

        max_portfolio_exposure = account.equity * config.max_portfolio_exposure

        portfolio_remaining = max_portfolio_exposure - current_portfolio_exposure

        # --------------------------------------------------------------
        # Existing symbol exposure
        # --------------------------------------------------------------

        current_symbol_exposure = calculate_symbol_exposure(
            context.positions,
            normalized_symbol,
            constraints,
        )

        max_symbol_exposure = account.equity * config.max_symbol_exposure

        symbol_remaining = max_symbol_exposure - current_symbol_exposure

        # --------------------------------------------------------------
        # Existing strategy exposure
        # --------------------------------------------------------------

        current_strategy_exposure = Decimal("0")

        for position in context.positions:
            if position.strategy_id != signal.strategy_id:
                continue

            position_symbol = position.symbol.strip().upper()

            position_constraints = context.constraints_by_symbol.get(
                position_symbol,
            )

            if position_constraints is None:
                raise RiskCalculationError(
                    "Missing symbol constraints for existing position "
                    f"{position_symbol}.",
                )

            if position_constraints.symbol != position_symbol:
                raise RiskCalculationError(
                    "Symbol constraint key does not match the constraint "
                    f"symbol. Key: {position_symbol}, "
                    f"constraints: {position_constraints.symbol}.",
                )

            current_strategy_exposure += calculate_position_risk_exposure(
                position,
                position_constraints,
            )

        max_strategy_exposure = account.equity * config.max_strategy_exposure

        strategy_remaining = max_strategy_exposure - current_strategy_exposure

        # --------------------------------------------------------------
        # Convert remaining exposure capacity to position-size capacity
        # --------------------------------------------------------------

        portfolio_position_cap = (
            portfolio_remaining / exposure_per_unit
            if portfolio_remaining > Decimal("0")
            else Decimal("0")
        )

        symbol_position_cap = (
            symbol_remaining / exposure_per_unit
            if symbol_remaining > Decimal("0")
            else Decimal("0")
        )

        strategy_position_cap = (
            strategy_remaining / exposure_per_unit
            if strategy_remaining > Decimal("0")
            else Decimal("0")
        )

        exposure_position_cap = min(
            portfolio_position_cap,
            symbol_position_cap,
            strategy_position_cap,
        )

        # --------------------------------------------------------------
        # Exposure cap cannot increase the risk-based position size
        # --------------------------------------------------------------

        if exposure_position_cap >= position_size:
            return position_size

        if exposure_position_cap <= Decimal("0"):
            return Decimal("0")

        # --------------------------------------------------------------
        # Normalize the reduced position to broker volume rules
        # --------------------------------------------------------------

        return RiskEngine._normalize_capped_position_size(
            position_size=exposure_position_cap,
            constraints=constraints,
        )

    # ------------------------------------------------------------------
    # Context validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_context(
        context: RiskContext,
    ) -> None:
        """Validate the minimum context required by the engine."""

        if context.account.equity <= Decimal("0"):
            raise RiskCalculationError(
                "Account equity must be greater than zero.",
            )

        if not context.signal.symbol.strip():
            raise RiskCalculationError(
                "Signal symbol cannot be empty.",
            )

        if context.market.bid <= Decimal("0") or context.market.ask <= Decimal("0"):
            raise RiskCalculationError(
                "Market bid and ask must be greater than zero.",
            )

        if context.market.ask < context.market.bid:
            raise RiskCalculationError(
                "Market ask cannot be below bid.",
            )

    # ------------------------------------------------------------------
    # Decimal normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _decimal(
        value: Decimal | int | float | str,
    ) -> Decimal:
        """
        Convert numeric values to Decimal.

        String conversion is intentional when receiving floats. It avoids
        importing the binary floating-point representation directly into
        Decimal arithmetic.
        """

        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))

    @staticmethod
    def _safe_decimal(
        value: Decimal | int | float | str,
    ) -> Decimal | None:
        """Best-effort Decimal conversion for diagnostic rejection data."""

        try:
            decimal_value = RiskEngine._decimal(value)

            if decimal_value <= Decimal("0"):
                return None

            return decimal_value

        except (
            TypeError,
            ValueError,
            ArithmeticError,
        ):
            return None

    # ------------------------------------------------------------------
    # Position-size normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_capped_position_size(
        *,
        position_size: Decimal,
        constraints: SymbolRiskConstraints,
    ) -> Decimal:
        """
        Normalize a reduced position size to broker volume rules.

        The result is always rounded DOWN so normalization can never
        increase the requested position size or violate an exposure cap.
        """

        if position_size <= Decimal("0"):
            return Decimal("0")

        minimum = constraints.volume_min
        maximum = constraints.volume_max
        step = constraints.volume_step

        if minimum <= Decimal("0"):
            raise RiskCalculationError(
                "Minimum volume must be greater than zero.",
            )

        if maximum < minimum:
            raise RiskCalculationError(
                "Maximum volume cannot be less than minimum volume.",
            )

        if step <= Decimal("0"):
            raise RiskCalculationError(
                "Broker volume step must be greater than zero.",
            )

        if position_size < minimum:
            return Decimal("0")

        if position_size > maximum:
            position_size = maximum

        steps = ((position_size - minimum) / step).to_integral_value(
            rounding=ROUND_FLOOR,
        )

        normalized = minimum + (steps * step)

        if normalized > maximum:
            normalized = maximum

        if normalized <= Decimal("0"):
            return Decimal("0")

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
    # Decision metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_metadata_value(
        value: Any,
    ) -> Any:
        """
        Convert Risk Engine diagnostic values into JSON-safe primitives.

        Strategy metadata itself is preserved unchanged. This helper is
        used only for values generated by the Risk Engine.
        """

        if isinstance(value, Decimal):
            return str(value)

        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except (TypeError, ValueError):
                pass

        if isinstance(value, dict):
            return {
                str(key): RiskEngine._serialize_metadata_value(
                    item,
                )
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [RiskEngine._serialize_metadata_value(item) for item in value]

        if isinstance(value, set):
            return [RiskEngine._serialize_metadata_value(item) for item in value]

        return value

    @classmethod
    def _build_decision_metadata(
        cls,
        context: RiskContext,
        *,
        target_risk_amount: Decimal | None = None,
        max_risk_amount: Decimal | None = None,
        initial_position_size: Decimal | None = None,
        position_size_after_config_caps: Decimal | None = None,
        final_position_size: Decimal | None = None,
        actual_risk: Decimal | None = None,
        portfolio_risk_before: Decimal | None = None,
        portfolio_risk_after: Decimal | None = None,
        max_portfolio_risk_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        """
        Preserve strategy metadata and add Risk Engine diagnostics.

        The strategy's metadata remains at the top level.

        Example:

            {
                "donchian_period": 20,
                "fast_ema": 42700.0,
                "breakout_distance_atr": 0.42,
                "risk_engine_diagnostics": {
                    ...
                },
            }
        """

        signal_metadata = context.signal.metadata or {}

        if not isinstance(signal_metadata, dict):
            signal_metadata = {
                "strategy_metadata": signal_metadata,
            }

        metadata: dict[str, Any] = dict(
            signal_metadata,
        )

        diagnostics: dict[str, Any] = {
            "risk_engine_version": "1.0",
            "target_risk_amount": target_risk_amount,
            "max_risk_amount": max_risk_amount,
            "initial_position_size": initial_position_size,
            "position_size_after_config_caps": (position_size_after_config_caps),
            "final_position_size": final_position_size,
            "actual_risk": actual_risk,
            "portfolio_risk_before": portfolio_risk_before,
            "portfolio_risk_after": portfolio_risk_after,
            "max_portfolio_risk_amount": max_portfolio_risk_amount,
        }

        metadata["risk_engine_diagnostics"] = {
            key: cls._serialize_metadata_value(value)
            for key, value in diagnostics.items()
            if value is not None
        }

        return metadata

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    @classmethod
    def _reject(
        cls,
        context: RiskContext,
        reason: RiskRejectionReason | None,
        message: str | None,
        *,
        risk_amount: Decimal = Decimal("0"),
        position_size: Decimal | None = None,
        entry_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        risk_reward_ratio: Decimal | None = None,
    ) -> RiskDecision:
        """
        Build a rejected RiskDecision while preserving calculated values
        and all strategy metadata.
        """

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
            risk_amount=risk_amount,
            position_size=position_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=risk_reward_ratio,
            rejection_reason=reason,
            message=message,
            metadata=cls._build_decision_metadata(
                context,
                target_risk_amount=risk_amount,
                final_position_size=position_size,
                actual_risk=(risk_amount if risk_amount > Decimal("0") else None),
            ),
        )