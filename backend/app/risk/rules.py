from decimal import Decimal

from app.risk.calculator import RiskCalculator
from app.risk.exceptions import (
    DailyLossLimitExceeded,
    DrawdownLimitExceeded,
    OpenRiskLimitExceeded,
    PositionLimitExceeded,
    StrategyExposureLimitExceeded,
    SymbolExposureLimitExceeded,
)
from app.risk.schemas import RiskCheckResponse


class RiskRules:
    """
    Hard risk rules applied before trade execution.

    This class receives the current account risk state and
    determines whether a proposed trade is allowed.
    """

    def __init__(
        self,
        profile,
    ):
        self.profile = profile

    # ==========================================================
    # RISK CHECK
    # ==========================================================

    def check(
        self,
        *,
        proposed_risk_amount: Decimal,
        proposed_symbol_exposure_amount: Decimal,
        proposed_strategy_exposure_amount: Decimal,
        current_open_risk_amount: Decimal,
        current_symbol_exposure_amount: Decimal,
        current_strategy_exposure_amount: Decimal,
        current_open_positions: int,
        account_equity: Decimal,
        daily_loss_amount: Decimal,
        drawdown_amount: Decimal,
    ) -> RiskCheckResponse:

        if account_equity <= 0:
            return RiskCheckResponse(
                allowed=False,
                risk_percent=Decimal("0.0000"),
                risk_amount=Decimal("0.00"),
                available_risk_amount=Decimal("0.00"),
                projected_open_risk_percent=Decimal("0.0000"),
                projected_symbol_exposure_percent=Decimal("0.0000"),
                projected_strategy_exposure_percent=Decimal("0.0000"),
                projected_daily_loss_percent=Decimal("0.0000"),
                projected_drawdown_percent=Decimal("0.0000"),
                projected_positions=current_open_positions,
                reason="Account equity must be greater than zero",
            )

        if proposed_risk_amount < 0:
            return RiskCheckResponse(
                allowed=False,
                risk_percent=Decimal("0.0000"),
                risk_amount=Decimal("0.00"),
                available_risk_amount=Decimal("0.00"),
                projected_open_risk_percent=Decimal("0.0000"),
                projected_symbol_exposure_percent=Decimal("0.0000"),
                projected_strategy_exposure_percent=Decimal("0.0000"),
                projected_daily_loss_percent=Decimal("0.0000"),
                projected_drawdown_percent=Decimal("0.0000"),
                projected_positions=current_open_positions,
                reason="Proposed risk amount cannot be negative",
            )

        # ======================================================
        # EFFECTIVE RISK
        # ======================================================

        effective_risk_percent = (
            RiskCalculator.effective_risk_percent(
                base_risk_percent=self.profile.base_risk_percent,
                risk_multiplier=self.profile.risk_multiplier,
                min_risk_percent=self.profile.min_risk_percent,
                max_risk_percent=self.profile.max_risk_percent,
            )
        )

        # ======================================================
        # PROJECTED VALUES
        # ======================================================

        projected_open_risk = (
            current_open_risk_amount
            + proposed_risk_amount
        )

        projected_symbol_exposure = (
            current_symbol_exposure_amount
            + proposed_symbol_exposure_amount
        )

        projected_strategy_exposure = (
            current_strategy_exposure_amount
            + proposed_strategy_exposure_amount
        )

        # A new trade whose stop is hit contributes its proposed
        # risk to the day's loss exposure.
        projected_daily_loss = (
            daily_loss_amount
            + proposed_risk_amount
        )

        # Likewise, the worst-case risk of the new trade must be
        # considered when checking drawdown capacity.
        projected_drawdown = (
            drawdown_amount
            + proposed_risk_amount
        )

        projected_positions = (
            current_open_positions
            + 1
        )

        # ======================================================
        # PROJECTED PERCENTAGES
        # ======================================================

        projected_open_risk_percent = (
            projected_open_risk
            / account_equity
            * Decimal("100")
        )

        projected_symbol_exposure_percent = (
            projected_symbol_exposure
            / account_equity
            * Decimal("100")
        )

        projected_strategy_exposure_percent = (
            projected_strategy_exposure
            / account_equity
            * Decimal("100")
        )

        projected_daily_loss_percent = (
            projected_daily_loss
            / account_equity
            * Decimal("100")
        )

        projected_drawdown_percent = (
            projected_drawdown
            / account_equity
            * Decimal("100")
        )

        # ======================================================
        # REMAINING OPEN-RISK CAPACITY
        # ======================================================

        maximum_open_risk_amount = (
            account_equity
            * self.profile.max_open_risk_percent
            / Decimal("100")
        )

        available_risk_amount = max(
            Decimal("0"),
            maximum_open_risk_amount
            - current_open_risk_amount,
        )

        # ======================================================
        # RISK PROFILE DISABLED
        # ======================================================

        if not self.profile.enabled:
            return RiskCheckResponse(
                allowed=False,
                risk_percent=effective_risk_percent,
                risk_amount=proposed_risk_amount,
                available_risk_amount=available_risk_amount.quantize(
                    Decimal("0.01")
                ),
                projected_open_risk_percent=projected_open_risk_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_symbol_exposure_percent=projected_symbol_exposure_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_strategy_exposure_percent=projected_strategy_exposure_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_daily_loss_percent=projected_daily_loss_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_drawdown_percent=projected_drawdown_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_positions=projected_positions,
                reason="Risk management is disabled",
            )

        # ======================================================
        # BASE RISK LIMIT
        # ======================================================

        if (
            self.profile.hard_limits_enabled
            and effective_risk_percent
            > self.profile.max_risk_percent
        ):
            return RiskCheckResponse(
                allowed=False,
                risk_percent=effective_risk_percent,
                risk_amount=proposed_risk_amount,
                available_risk_amount=available_risk_amount.quantize(
                    Decimal("0.01")
                ),
                projected_open_risk_percent=projected_open_risk_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_symbol_exposure_percent=projected_symbol_exposure_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_strategy_exposure_percent=projected_strategy_exposure_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_daily_loss_percent=projected_daily_loss_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_drawdown_percent=projected_drawdown_percent.quantize(
                    Decimal("0.0001")
                ),
                projected_positions=projected_positions,
                reason="Effective risk exceeds maximum allowed risk",
            )

        # ======================================================
        # OPEN RISK
        # ======================================================

        if (
            self.profile.hard_limits_enabled
            and projected_open_risk_percent
            > self.profile.max_open_risk_percent
        ):
            raise OpenRiskLimitExceeded(
                "Maximum aggregate open risk would be exceeded"
            )

        # ======================================================
        # DAILY LOSS
        # ======================================================

        if (
            self.profile.hard_limits_enabled
            and projected_daily_loss_percent
            > self.profile.max_daily_loss_percent
        ):
            raise DailyLossLimitExceeded(
                "Maximum daily loss would be exceeded"
            )

        # ======================================================
        # DRAWDOWN
        # ======================================================

        if (
            self.profile.hard_limits_enabled
            and projected_drawdown_percent
            > self.profile.max_drawdown_percent
        ):
            raise DrawdownLimitExceeded(
                "Maximum drawdown would be exceeded"
            )

        # ======================================================
        # POSITION COUNT
        # ======================================================

        if (
            projected_positions
            > self.profile.max_positions
        ):
            raise PositionLimitExceeded(
                "Maximum number of open positions would be exceeded"
            )

        # ======================================================
        # SYMBOL EXPOSURE
        # ======================================================

        if (
            projected_symbol_exposure_percent
            > self.profile.max_symbol_exposure_percent
        ):
            raise SymbolExposureLimitExceeded(
                "Maximum symbol exposure would be exceeded"
            )

        # ======================================================
        # STRATEGY EXPOSURE
        # ======================================================

        if (
            projected_strategy_exposure_percent
            > self.profile.max_strategy_exposure_percent
        ):
            raise StrategyExposureLimitExceeded(
                "Maximum strategy exposure would be exceeded"
            )

        # ======================================================
        # APPROVED
        # ======================================================

        return RiskCheckResponse(
            allowed=True,
            risk_percent=effective_risk_percent,
            risk_amount=proposed_risk_amount.quantize(
                Decimal("0.01")
            ),
            available_risk_amount=available_risk_amount.quantize(
                Decimal("0.01")
            ),
            projected_open_risk_percent=projected_open_risk_percent.quantize(
                Decimal("0.0001")
            ),
            projected_symbol_exposure_percent=projected_symbol_exposure_percent.quantize(
                Decimal("0.0001")
            ),
            projected_strategy_exposure_percent=projected_strategy_exposure_percent.quantize(
                Decimal("0.0001")
            ),
            projected_daily_loss_percent=projected_daily_loss_percent.quantize(
                Decimal("0.0001")
            ),
            projected_drawdown_percent=projected_drawdown_percent.quantize(
                Decimal("0.0001")
            ),
            projected_positions=projected_positions,
            reason=None,
        )