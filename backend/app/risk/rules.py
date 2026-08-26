from decimal import Decimal

from app.risk.decision import RiskDecision
from app.risk.exceptions import InvalidRiskConfiguration
from app.risk.models import RiskProfile
from app.risk.state import RiskState


class RiskRules:
    """
    Pure risk-rule evaluation.

    Responsibilities:
    - Evaluate a proposed trade against the RiskProfile.
    - Evaluate the current server-side RiskState.
    - Return structured RiskDecision objects.

    This class does not:
    - access the database,
    - access brokers,
    - access HTTP,
    - modify positions,
    - execute orders.

    All persistence and orchestration belongs to RiskService.
    """

    def __init__(
        self,
        profile: RiskProfile,
    ):
        self.profile = profile

        self._validate_profile()

    # ==========================================================
    # PROFILE VALIDATION
    # ==========================================================

    def _validate_profile(self) -> None:
        """
        Validate the minimum configuration required by the rules.
        """

        if self.profile.min_risk_percent <= 0:
            raise InvalidRiskConfiguration("Minimum risk must be greater than zero")

        if self.profile.base_risk_percent <= 0:
            raise InvalidRiskConfiguration("Base risk must be greater than zero")

        if self.profile.max_risk_percent <= 0:
            raise InvalidRiskConfiguration("Maximum risk must be greater than zero")

        if self.profile.min_risk_percent > self.profile.base_risk_percent:
            raise InvalidRiskConfiguration(
                "Minimum risk cannot be greater than base risk"
            )

        if self.profile.base_risk_percent > self.profile.max_risk_percent:
            raise InvalidRiskConfiguration(
                "Base risk cannot be greater than maximum risk"
            )

        if self.profile.risk_multiplier <= 0:
            raise InvalidRiskConfiguration("Risk multiplier must be greater than zero")

        if self.profile.max_daily_loss_percent <= 0:
            raise InvalidRiskConfiguration(
                "Maximum daily loss must be greater than zero"
            )

        if self.profile.max_drawdown_percent <= 0:
            raise InvalidRiskConfiguration("Maximum drawdown must be greater than zero")

        if self.profile.max_open_risk_percent <= 0:
            raise InvalidRiskConfiguration(
                "Maximum open risk must be greater than zero"
            )

    # ==========================================================
    # EFFECTIVE RISK
    # ==========================================================

    def effective_risk_percent(self) -> Decimal:
        """
        Calculate the effective risk percentage.

        The calculator is intentionally kept outside this class.
        RiskRules only evaluates limits and decisions.
        """

        requested = self.profile.base_risk_percent * self.profile.risk_multiplier

        if requested < self.profile.min_risk_percent:
            requested = self.profile.min_risk_percent

        if requested > self.profile.max_risk_percent:
            requested = self.profile.max_risk_percent

        return requested

    # ==========================================================
    # ACCOUNT ENABLEMENT
    # ==========================================================

    def check_enabled(self) -> RiskDecision:
        """
        Determine whether risk management is enabled.
        """

        if not self.profile.enabled:
            return RiskDecision.reject(
                code="RISK_MANAGEMENT_DISABLED",
                message=("Risk management is disabled " "for this trading account"),
            )

        return RiskDecision.approve(
            code="RISK_MANAGEMENT_ENABLED",
            message="Risk management is enabled",
        )

    # ==========================================================
    # DAILY LOSS
    # ==========================================================

    def check_daily_loss(
        self,
        state: RiskState,
    ) -> RiskDecision:
        """
        Check the account's daily loss limit.

        A proposed trade cannot be approved if the account
        has already reached its daily loss limit.
        """

        if state.equity <= 0:
            return RiskDecision.reject(
                code="INVALID_EQUITY",
                message="Account equity must be greater than zero",
            )

        daily_loss_percent = state.daily_loss_amount / state.equity * Decimal("100")

        if daily_loss_percent >= self.profile.max_daily_loss_percent:
            return RiskDecision.reject(
                code="DAILY_LOSS_LIMIT_EXCEEDED",
                message=("Account daily loss limit has been exceeded"),
                metadata={
                    "daily_loss_amount": state.daily_loss_amount,
                    "daily_loss_percent": daily_loss_percent,
                    "max_daily_loss_percent": (self.profile.max_daily_loss_percent),
                },
            )

        return RiskDecision.approve(
            code="DAILY_LOSS_LIMIT_OK",
            message="Daily loss limit has not been exceeded",
        )

    # ==========================================================
    # DRAWDOWN
    # ==========================================================

    def check_drawdown(
        self,
        state: RiskState,
    ) -> RiskDecision:
        """
        Check maximum account drawdown.
        """

        if state.equity <= 0:
            return RiskDecision.reject(
                code="INVALID_EQUITY",
                message="Account equity must be greater than zero",
            )

        drawdown_percent = state.drawdown_amount / state.equity * Decimal("100")

        if drawdown_percent >= self.profile.max_drawdown_percent:
            return RiskDecision.reject(
                code="DRAWDOWN_LIMIT_EXCEEDED",
                message=("Maximum account drawdown " "has been exceeded"),
                metadata={
                    "drawdown_amount": state.drawdown_amount,
                    "drawdown_percent": drawdown_percent,
                    "max_drawdown_percent": (self.profile.max_drawdown_percent),
                },
            )

        return RiskDecision.approve(
            code="DRAWDOWN_LIMIT_OK",
            message="Maximum drawdown limit has not been exceeded",
        )

    # ==========================================================
    # OPEN RISK
    # ==========================================================

    def check_open_risk(
        self,
        state: RiskState,
        proposed_risk_amount: Decimal,
    ) -> RiskDecision:
        """
        Check aggregate open risk.

        Existing open risk + proposed trade risk must not
        exceed the account's configured open-risk limit.
        """

        if proposed_risk_amount <= 0:
            return RiskDecision.reject(
                code="INVALID_PROPOSED_RISK",
                message=("Proposed risk amount must be " "greater than zero"),
            )

        if state.equity <= 0:
            return RiskDecision.reject(
                code="INVALID_EQUITY",
                message="Account equity must be greater than zero",
            )

        total_open_risk = state.total_open_risk + proposed_risk_amount

        total_open_risk_percent = total_open_risk / state.equity * Decimal("100")

        if total_open_risk_percent > self.profile.max_open_risk_percent:
            return RiskDecision.reject(
                code="OPEN_RISK_LIMIT_EXCEEDED",
                message=("Proposed trade would exceed " "the maximum open-risk limit"),
                metadata={
                    "current_open_risk": state.total_open_risk,
                    "proposed_risk_amount": (proposed_risk_amount),
                    "total_open_risk": total_open_risk,
                    "total_open_risk_percent": (total_open_risk_percent),
                    "max_open_risk_percent": (self.profile.max_open_risk_percent),
                },
            )

        return RiskDecision.approve(
            code="OPEN_RISK_LIMIT_OK",
            message="Open-risk limit has not been exceeded",
            metadata={
                "total_open_risk": total_open_risk,
                "total_open_risk_percent": (total_open_risk_percent),
            },
        )

    # ==========================================================
    # POSITION LIMIT
    # ==========================================================

    def check_position_limit(
        self,
        state: RiskState,
    ) -> RiskDecision:
        """
        Check maximum number of open positions.
        """

        max_positions = self.profile.max_open_positions

        if max_positions is None:
            return RiskDecision.approve(
                code="POSITION_LIMIT_NOT_CONFIGURED",
                message="No maximum position limit is configured",
            )

        if state.open_positions >= max_positions:
            return RiskDecision.reject(
                code="POSITION_LIMIT_EXCEEDED",
                message=("Maximum number of open positions " "has been reached"),
                metadata={
                    "open_positions": state.open_positions,
                    "max_open_positions": max_positions,
                },
            )

        return RiskDecision.approve(
            code="POSITION_LIMIT_OK",
            message="Position limit has not been exceeded",
        )

    # ==========================================================
    # SYMBOL EXPOSURE
    # ==========================================================

    def check_symbol_exposure(
        self,
        state: RiskState,
        proposed_symbol_exposure_amount: Decimal,
    ) -> RiskDecision:
        """
        Check symbol-level exposure.
        """

        max_symbol_exposure = self.profile.max_symbol_exposure_percent

        if max_symbol_exposure is None:
            return RiskDecision.approve(
                code="SYMBOL_EXPOSURE_LIMIT_NOT_CONFIGURED",
                message=("No symbol exposure limit is configured"),
            )

        if state.equity <= 0:
            return RiskDecision.reject(
                code="INVALID_EQUITY",
                message="Account equity must be greater than zero",
            )

        total_symbol_exposure = (
            state.symbol_exposure_amount + proposed_symbol_exposure_amount
        )

        exposure_percent = total_symbol_exposure / state.equity * Decimal("100")

        if exposure_percent > max_symbol_exposure:
            return RiskDecision.reject(
                code="SYMBOL_EXPOSURE_LIMIT_EXCEEDED",
                message=("Proposed trade would exceed " "the symbol exposure limit"),
                metadata={
                    "current_symbol_exposure": (state.symbol_exposure_amount),
                    "proposed_symbol_exposure": (proposed_symbol_exposure_amount),
                    "total_symbol_exposure": (total_symbol_exposure),
                    "exposure_percent": exposure_percent,
                    "max_symbol_exposure_percent": (max_symbol_exposure),
                },
            )

        return RiskDecision.approve(
            code="SYMBOL_EXPOSURE_LIMIT_OK",
            message="Symbol exposure limit has not been exceeded",
        )

    # ==========================================================
    # STRATEGY EXPOSURE
    # ==========================================================

    def check_strategy_exposure(
        self,
        state: RiskState,
        proposed_strategy_exposure_amount: Decimal,
    ) -> RiskDecision:
        """
        Check strategy-level exposure.
        """

        max_strategy_exposure = self.profile.max_strategy_exposure_percent

        if max_strategy_exposure is None:
            return RiskDecision.approve(
                code="STRATEGY_EXPOSURE_LIMIT_NOT_CONFIGURED",
                message=("No strategy exposure limit is configured"),
            )

        if state.equity <= 0:
            return RiskDecision.reject(
                code="INVALID_EQUITY",
                message="Account equity must be greater than zero",
            )

        total_strategy_exposure = (
            state.strategy_exposure_amount + proposed_strategy_exposure_amount
        )

        exposure_percent = total_strategy_exposure / state.equity * Decimal("100")

        if exposure_percent > max_strategy_exposure:
            return RiskDecision.reject(
                code="STRATEGY_EXPOSURE_LIMIT_EXCEEDED",
                message=("Proposed trade would exceed " "the strategy exposure limit"),
                metadata={
                    "current_strategy_exposure": (state.strategy_exposure_amount),
                    "proposed_strategy_exposure": (proposed_strategy_exposure_amount),
                    "total_strategy_exposure": (total_strategy_exposure),
                    "exposure_percent": exposure_percent,
                    "max_strategy_exposure_percent": (max_strategy_exposure),
                },
            )

        return RiskDecision.approve(
            code="STRATEGY_EXPOSURE_LIMIT_OK",
            message=("Strategy exposure limit " "has not been exceeded"),
        )

    # ==========================================================
    # COMPLETE TRADE CHECK
    # ==========================================================

    def check(
        self,
        *,
        state: RiskState,
        proposed_risk_amount: Decimal,
        proposed_symbol_exposure_amount: Decimal = Decimal("0"),
        proposed_strategy_exposure_amount: Decimal = Decimal("0"),
    ) -> RiskDecision:
        """
        Evaluate a proposed trade against all applicable
        account-level risk rules.

        The first rejection is returned.

        This method is intentionally deterministic and has
        no persistence or external side effects.
        """

        decision = self.check_enabled()

        if decision.is_rejected:
            return decision

        decision = self.check_daily_loss(state)

        if decision.is_rejected:
            return decision

        decision = self.check_drawdown(state)

        if decision.is_rejected:
            return decision

        decision = self.check_position_limit(state)

        if decision.is_rejected:
            return decision

        decision = self.check_open_risk(
            state=state,
            proposed_risk_amount=proposed_risk_amount,
        )

        if decision.is_rejected:
            return decision

        decision = self.check_symbol_exposure(
            state=state,
            proposed_symbol_exposure_amount=(proposed_symbol_exposure_amount),
        )

        if decision.is_rejected:
            return decision

        decision = self.check_strategy_exposure(
            state=state,
            proposed_strategy_exposure_amount=(proposed_strategy_exposure_amount),
        )

        if decision.is_rejected:
            return decision

        return RiskDecision.approve(
            code="TRADE_APPROVED",
            message=("Trade passed all configured risk rules"),
        )
