"""Exposure-related risk rules."""

from __future__ import annotations

from decimal import Decimal

from ..calculators.exposure import (
    calculate_position_risk_exposure,
    calculate_symbol_exposure,
    calculate_total_exposure,
)
from ..enums import RiskRejectionReason
from ..exceptions import RiskCalculationError
from ..models import RiskContext, SymbolRiskConstraints
from .base import RiskRule, RuleResult


class ExposureRiskRule(RiskRule):
    """Validate portfolio, symbol, and strategy exposure."""

    name = "exposure_risk"

    def evaluate(self, context: RiskContext) -> RuleResult:
        """
        Evaluate notional exposure including the proposed trade.

        Existing positions and the proposed position are evaluated
        together so a new trade cannot push exposure beyond a configured
        portfolio, symbol, or strategy exposure limit.

        Notional exposure is calculated as:

            quantity × price × contract_size

        Exposure limits are distinct from monetary risk limits such as
        max_risk_per_trade and max_portfolio_risk.

        Every existing position must have a corresponding symbol
        constraint. The rule never falls back to the proposed signal's
        constraints for another symbol because doing so could calculate
        exposure using the wrong contract size.
        """

        if context.proposed_position_size is None:
            return RuleResult.reject(
                RiskRejectionReason.INVALID_POSITION_SIZE,
                "Proposed position size is required for exposure evaluation.",
            )

        account = context.account
        config = context.config
        signal = context.signal
        constraints = context.symbol_constraints

        # --------------------------------------------------------------
        # Validate the proposed symbol constraints
        # --------------------------------------------------------------

        normalized_signal_symbol = signal.symbol.strip().upper()

        if constraints.symbol != normalized_signal_symbol:
            raise RiskCalculationError(
                "Risk context symbol constraints do not match the "
                f"signal symbol. Signal: {normalized_signal_symbol}, "
                f"constraints: {constraints.symbol}."
            )

        # --------------------------------------------------------------
        # Proposed trade exposure
        # --------------------------------------------------------------

        proposed_exposure = (
            context.proposed_position_size
            * context.entry_price
            * constraints.contract_size
        )

        if proposed_exposure < Decimal("0"):
            raise RiskCalculationError("Proposed exposure cannot be negative.")

        # --------------------------------------------------------------
        # Existing portfolio exposure
        #
        # calculate_total_exposure() requires constraints for every
        # existing position symbol. Do not silently substitute the
        # proposed symbol's constraints.
        # --------------------------------------------------------------

        current_portfolio_exposure = calculate_total_exposure(
            context.positions,
            context.constraints_by_symbol,
        )

        # --------------------------------------------------------------
        # Existing exposure for the proposed symbol
        # --------------------------------------------------------------

        current_symbol_exposure = calculate_symbol_exposure(
            context.positions,
            normalized_signal_symbol,
            constraints,
        )

        # --------------------------------------------------------------
        # Existing exposure for the proposed strategy
        #
        # Every position belonging to this strategy must use the
        # constraints belonging to that position's own symbol.
        # --------------------------------------------------------------

        current_strategy_exposure = Decimal("0")

        for position in context.positions:
            if position.strategy_id != signal.strategy_id:
                continue

            position_symbol = position.symbol.strip().upper()

            position_constraints = self._get_constraints_for_position(
                context,
                position_symbol,
            )

            current_strategy_exposure += calculate_position_risk_exposure(
                position,
                position_constraints,
            )

        # --------------------------------------------------------------
        # Exposure after accepting the proposed trade
        # --------------------------------------------------------------

        proposed_portfolio_exposure = current_portfolio_exposure + proposed_exposure

        proposed_symbol_exposure = current_symbol_exposure + proposed_exposure

        proposed_strategy_exposure = current_strategy_exposure + proposed_exposure

        # --------------------------------------------------------------
        # Exposure limits
        #
        # These are multiples of account equity, not percentages of
        # monetary risk.
        # --------------------------------------------------------------

        max_portfolio_exposure = account.equity * config.max_portfolio_exposure

        max_symbol_exposure = account.equity * config.max_symbol_exposure

        max_strategy_exposure = account.equity * config.max_strategy_exposure

        # --------------------------------------------------------------
        # Portfolio exposure
        # --------------------------------------------------------------

        if proposed_portfolio_exposure > max_portfolio_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_PORTFOLIO_EXPOSURE,
                (
                    "The proposed trade would exceed the maximum "
                    "portfolio exposure. "
                    f"Current: {current_portfolio_exposure}, "
                    f"proposed: {proposed_portfolio_exposure}, "
                    f"maximum: {max_portfolio_exposure}."
                ),
            )

        # --------------------------------------------------------------
        # Symbol exposure
        # --------------------------------------------------------------

        if proposed_symbol_exposure > max_symbol_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_SYMBOL_EXPOSURE,
                (
                    f"The proposed {normalized_signal_symbol} trade would "
                    "exceed the maximum symbol exposure. "
                    f"Current: {current_symbol_exposure}, "
                    f"proposed: {proposed_symbol_exposure}, "
                    f"maximum: {max_symbol_exposure}."
                ),
            )

        # --------------------------------------------------------------
        # Strategy exposure
        # --------------------------------------------------------------

        if proposed_strategy_exposure > max_strategy_exposure:
            return RuleResult.reject(
                RiskRejectionReason.MAX_STRATEGY_EXPOSURE,
                (
                    "The proposed trade for strategy "
                    f"{signal.strategy_id} would exceed the maximum "
                    "strategy exposure. "
                    f"Current: {current_strategy_exposure}, "
                    f"proposed: {proposed_strategy_exposure}, "
                    f"maximum: {max_strategy_exposure}."
                ),
            )

        return RuleResult.pass_()

    @staticmethod
    def _get_constraints_for_position(
        context: RiskContext,
        symbol: str,
    ) -> SymbolRiskConstraints:
        """
        Return constraints for an existing position.

        Constraint lookup is deliberately strict. Using another symbol's
        contract size could materially distort notional exposure and cause
        an incorrect risk decision.
        """

        constraints = context.constraints_by_symbol.get(symbol)

        if constraints is None:
            raise RiskCalculationError(
                f"Missing symbol constraints for existing position " f"{symbol}."
            )

        if constraints.symbol != symbol:
            raise RiskCalculationError(
                "Symbol constraint key does not match the constraint "
                f"symbol. Key: {symbol}, constraints: {constraints.symbol}."
            )

        return constraints
