from decimal import Decimal
from uuid import UUID

from app.risk.calculator import RiskCalculator
from app.risk.exceptions import (
    InvalidRiskConfiguration,
    RiskProfileNotFound,
)
from app.risk.repository import (
    RiskProfileRepository,
)
from app.risk.rules import RiskRules
from app.risk.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
    RiskProfileCreate,
    RiskProfileResponse,
    RiskProfileUpdate,
    RiskSizingRequest,
    RiskSizingResponse,
)


class RiskService:
    """
    Application service for account risk management.

    Responsibilities:

    - Manage account risk profiles.
    - Calculate effective risk.
    - Calculate risk-based position sizing.
    - Enforce account-level risk limits.
    """

    def __init__(
        self,
        repository: RiskProfileRepository,
    ):
        self.repository = repository

    # ==========================================================
    # PROFILE VALIDATION
    # ==========================================================

    @staticmethod
    def _validate_profile_values(
        *,
        min_risk_percent: Decimal,
        base_risk_percent: Decimal,
        max_risk_percent: Decimal,
        risk_multiplier: Decimal | None = None,
        max_daily_loss_percent: Decimal | None = None,
        max_drawdown_percent: Decimal | None = None,
        max_open_risk_percent: Decimal | None = None,
    ) -> None:

        if min_risk_percent <= 0:
            raise InvalidRiskConfiguration(
                "Minimum risk must be greater than zero"
            )

        if base_risk_percent <= 0:
            raise InvalidRiskConfiguration(
                "Base risk must be greater than zero"
            )

        if max_risk_percent <= 0:
            raise InvalidRiskConfiguration(
                "Maximum risk must be greater than zero"
            )

        if (
            min_risk_percent
            > base_risk_percent
        ):
            raise InvalidRiskConfiguration(
                "Minimum risk cannot be greater than base risk"
            )

        if (
            base_risk_percent
            > max_risk_percent
        ):
            raise InvalidRiskConfiguration(
                "Base risk cannot be greater than maximum risk"
            )

        if risk_multiplier is not None:
            if risk_multiplier <= 0:
                raise InvalidRiskConfiguration(
                    "Risk multiplier must be greater than zero"
                )

        if max_daily_loss_percent is not None:
            if max_daily_loss_percent <= 0:
                raise InvalidRiskConfiguration(
                    "Maximum daily loss must be greater than zero"
                )

        if max_drawdown_percent is not None:
            if max_drawdown_percent <= 0:
                raise InvalidRiskConfiguration(
                    "Maximum drawdown must be greater than zero"
                )

        if max_open_risk_percent is not None:
            if max_open_risk_percent <= 0:
                raise InvalidRiskConfiguration(
                    "Maximum open risk must be greater than zero"
                )

    # ==========================================================
    # CREATE PROFILE
    # ==========================================================

    async def create_profile(
        self,
        data: RiskProfileCreate,
    ) -> RiskProfileResponse:

        self._validate_profile_values(
            min_risk_percent=data.min_risk_percent,
            base_risk_percent=data.base_risk_percent,
            max_risk_percent=data.max_risk_percent,
            risk_multiplier=data.risk_multiplier,
            max_daily_loss_percent=(
                data.max_daily_loss_percent
            ),
            max_drawdown_percent=(
                data.max_drawdown_percent
            ),
            max_open_risk_percent=(
                data.max_open_risk_percent
            ),
        )

        if (
            data.max_open_risk_percent
            < data.max_risk_percent
        ):
            raise InvalidRiskConfiguration(
                "Maximum open risk cannot be lower than "
                "maximum risk per trade"
            )

        existing = (
            await self.repository.get_by_account(
                data.account_id
            )
        )

        if existing:
            raise InvalidRiskConfiguration(
                "A risk profile already exists for this account"
            )

        profile = await self.repository.create(
            **data.model_dump()
        )

        return RiskProfileResponse.model_validate(
            profile
        )

    # ==========================================================
    # GET PROFILE
    # ==========================================================

    async def get_profile(
        self,
        account_id: UUID,
    ) -> RiskProfileResponse:

        profile = (
            await self.repository.get_by_account(
                account_id
            )
        )

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account "
                f"{account_id}"
            )

        return RiskProfileResponse.model_validate(
            profile
        )

    # ==========================================================
    # UPDATE PROFILE
    # ==========================================================

    async def update_profile(
        self,
        account_id: UUID,
        data: RiskProfileUpdate,
    ) -> RiskProfileResponse:

        profile = (
            await self.repository.get_by_account(
                account_id
            )
        )

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account "
                f"{account_id}"
            )

        values = data.model_dump(
            exclude_unset=True
        )

        min_risk = values.get(
            "min_risk_percent",
            profile.min_risk_percent,
        )

        base_risk = values.get(
            "base_risk_percent",
            profile.base_risk_percent,
        )

        max_risk = values.get(
            "max_risk_percent",
            profile.max_risk_percent,
        )

        risk_multiplier = values.get(
            "risk_multiplier",
            profile.risk_multiplier,
        )

        max_daily_loss = values.get(
            "max_daily_loss_percent",
            profile.max_daily_loss_percent,
        )

        max_drawdown = values.get(
            "max_drawdown_percent",
            profile.max_drawdown_percent,
        )

        max_open_risk = values.get(
            "max_open_risk_percent",
            profile.max_open_risk_percent,
        )

        self._validate_profile_values(
            min_risk_percent=min_risk,
            base_risk_percent=base_risk,
            max_risk_percent=max_risk,
            risk_multiplier=risk_multiplier,
            max_daily_loss_percent=max_daily_loss,
            max_drawdown_percent=max_drawdown,
            max_open_risk_percent=max_open_risk,
        )

        if max_open_risk < max_risk:
            raise InvalidRiskConfiguration(
                "Maximum open risk cannot be lower than "
                "maximum risk per trade"
            )

        profile = await self.repository.update(
            profile,
            **values,
        )

        return RiskProfileResponse.model_validate(
            profile
        )

    # ==========================================================
    # EFFECTIVE RISK
    # ==========================================================

    async def get_effective_risk_percent(
        self,
        account_id: UUID,
    ) -> Decimal:

        profile = (
            await self.repository.get_by_account(
                account_id
            )
        )

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account "
                f"{account_id}"
            )

        return RiskCalculator.effective_risk_percent(
            base_risk_percent=profile.base_risk_percent,
            risk_multiplier=profile.risk_multiplier,
            min_risk_percent=profile.min_risk_percent,
            max_risk_percent=profile.max_risk_percent,
        )

    # ==========================================================
    # POSITION SIZE
    # ==========================================================

    async def calculate_position_size(
        self,
        data: RiskSizingRequest,
        account_equity: Decimal,
    ) -> RiskSizingResponse:

        profile = (
            await self.repository.get_by_account(
                data.account_id
            )
        )

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account "
                f"{data.account_id}"
            )

        if not profile.enabled:
            raise InvalidRiskConfiguration(
                "Risk management is disabled for this account"
            )

        risk_percent = (
            RiskCalculator.effective_risk_percent(
                base_risk_percent=profile.base_risk_percent,
                risk_multiplier=profile.risk_multiplier,
                min_risk_percent=profile.min_risk_percent,
                max_risk_percent=profile.max_risk_percent,
            )
        )

        risk_amount = (
            RiskCalculator.risk_amount(
                equity=account_equity,
                risk_percent=risk_percent,
            )
        )

        stop_distance = (
            RiskCalculator.stop_distance(
                entry_price=data.entry_price,
                stop_loss_price=data.stop_loss_price,
            )
        )

        risk_per_unit = (
            RiskCalculator.risk_per_unit(
                stop_distance=stop_distance,
                tick_size=data.tick_size,
                tick_value=data.tick_value,
            )
        )

        raw_volume = (
            risk_amount
            / risk_per_unit
        )

        recommended_volume = (
            RiskCalculator.position_size(
                risk_amount=risk_amount,
                risk_per_unit=risk_per_unit,
            )
        )

        return RiskSizingResponse(
            risk_percent=risk_percent,
            risk_multiplier=profile.risk_multiplier,
            risk_amount=risk_amount,
            entry_price=data.entry_price,
            stop_loss_price=data.stop_loss_price,
            stop_distance=stop_distance,
            tick_size=data.tick_size,
            tick_value=data.tick_value,
            raw_volume=raw_volume.quantize(
                Decimal("0.00000001")
            ),
            recommended_volume=recommended_volume,
            risk_per_unit=risk_per_unit,
        )

    # ==========================================================
    # RISK CHECK
    # ==========================================================

    async def check_trade(
        self,
        data: RiskCheckRequest,
    ) -> RiskCheckResponse:

        profile = (
            await self.repository.get_by_account(
                data.account_id
            )
        )

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account "
                f"{data.account_id}"
            )

        rules = RiskRules(
            profile
        )

        return rules.check(
            proposed_risk_amount=(
                data.proposed_risk_amount
            ),
            proposed_symbol_exposure_amount=(
                data.proposed_symbol_exposure_amount
            ),
            proposed_strategy_exposure_amount=(
                data.proposed_strategy_exposure_amount
            ),
            current_open_risk_amount=(
                data.current_open_risk_amount
            ),
            current_symbol_exposure_amount=(
                data.current_symbol_exposure_amount
            ),
            current_strategy_exposure_amount=(
                data.current_strategy_exposure_amount
            ),
            current_open_positions=(
                data.current_open_positions
            ),
            account_equity=data.account_equity,
            daily_loss_amount=data.daily_loss_amount,
            drawdown_amount=data.drawdown_amount,
        )