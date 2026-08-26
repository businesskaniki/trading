from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.constants import PositionStatus

from app.risk.calculator import RiskCalculator
from app.risk.exceptions import (
    InvalidRiskConfiguration,
    RiskProfileNotFound,
)
from app.risk.repository import RiskProfileRepository
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

from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.repositories.symbol_repository import (
    SymbolRepository,
)
from app.repositories.position_repository import (
    PositionRepository,
)

# ==============================================================
# SERVER-SIDE RISK STATE
# ==============================================================


@dataclass
class RiskState:
    """
    Server-side representation of the current risk state
    of a trading account.

    This object is NOT persisted directly.

    It is constructed from the database and represents the
    current state that the Risk Engine uses when evaluating
    a proposed trade.
    """

    # ----------------------------------------------------------
    # Account
    # ----------------------------------------------------------

    account_id: UUID

    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal

    # ----------------------------------------------------------
    # Open positions
    # ----------------------------------------------------------

    open_positions: int
    total_volume: Decimal

    # ----------------------------------------------------------
    # Risk
    # ----------------------------------------------------------

    total_open_risk: Decimal
    total_exposure: Decimal

    # ----------------------------------------------------------
    # Daily / drawdown
    #
    # These are currently derived from available position/account
    # information. Later they should be connected to the account
    # equity history / risk snapshots.
    # ----------------------------------------------------------

    floating_profit_loss: Decimal
    daily_loss_amount: Decimal
    drawdown_amount: Decimal
    symbol_exposure_amount: Decimal = Decimal("0")
    strategy_exposure_amount: Decimal = Decimal("0")


class RiskService:
    """
    Application service / orchestrator for the AQE Risk Engine.

    Responsibilities
    ----------------

    1. Manage risk profiles.
    2. Load the trading account from the database.
    3. Load symbol information from the database.
    4. Build the current server-side RiskState.
    5. Calculate effective risk.
    6. Calculate position sizing.
    7. Evaluate proposed trades against risk rules.

    Important
    ---------

    The frontend must NOT be trusted to provide current:

        - account equity
        - open positions
        - open risk
        - exposure
        - daily loss
        - drawdown

    Those values are reconstructed server-side.
    """

    def __init__(
        self,
        risk_repository: RiskProfileRepository,
        trading_account_repository: TradingAccountRepository,
        symbol_repository: SymbolRepository,
        position_repository: PositionRepository,
    ):
        self.risk_repository = risk_repository
        self.trading_account_repository = trading_account_repository
        self.symbol_repository = symbol_repository
        self.position_repository = position_repository

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
            raise InvalidRiskConfiguration("Minimum risk must be greater than zero")

        if base_risk_percent <= 0:
            raise InvalidRiskConfiguration("Base risk must be greater than zero")

        if max_risk_percent <= 0:
            raise InvalidRiskConfiguration("Maximum risk must be greater than zero")

        if min_risk_percent > base_risk_percent:
            raise InvalidRiskConfiguration(
                "Minimum risk cannot be greater than base risk"
            )

        if base_risk_percent > max_risk_percent:
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
            max_daily_loss_percent=data.max_daily_loss_percent,
            max_drawdown_percent=data.max_drawdown_percent,
            max_open_risk_percent=data.max_open_risk_percent,
        )

        if data.max_open_risk_percent < data.max_risk_percent:
            raise InvalidRiskConfiguration(
                "Maximum open risk cannot be lower than " "maximum risk per trade"
            )

        existing = await self.risk_repository.get_by_account(data.account_id)

        if existing:
            raise InvalidRiskConfiguration(
                "A risk profile already exists for this account"
            )

        # ------------------------------------------------------
        # Verify trading account exists
        # ------------------------------------------------------

        account = await self.trading_account_repository.get_by_id(data.account_id)

        if not account:
            raise InvalidRiskConfiguration(
                f"Trading account {data.account_id} does not exist"
            )

        create_values = data.model_dump()
        create_values["max_positions"] = create_values.pop("max_open_positions")

        profile = await self.risk_repository.create(**create_values)

        return RiskProfileResponse.model_validate(profile)

    # ==========================================================
    # GET PROFILE
    # ==========================================================

    async def get_profile(
        self,
        account_id: UUID,
    ) -> RiskProfileResponse:

        profile = await self.risk_repository.get_by_account(account_id)

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account " f"{account_id}"
            )

        return RiskProfileResponse.model_validate(profile)

    # ==========================================================
    # UPDATE PROFILE
    # ==========================================================

    async def update_profile(
        self,
        account_id: UUID,
        data: RiskProfileUpdate,
    ) -> RiskProfileResponse:

        profile = await self.risk_repository.get_by_account(account_id)

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account " f"{account_id}"
            )

        values = data.model_dump(exclude_unset=True)

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
                "Maximum open risk cannot be lower than " "maximum risk per trade"
            )

        profile = await self.risk_repository.update(
            profile,
            **values,
        )

        return RiskProfileResponse.model_validate(profile)

    # ==========================================================
    # LOAD ACCOUNT
    # ==========================================================

    async def _get_account(
        self,
        account_id: UUID,
    ):
        """
        Load the trading account from the database.

        Centralized so every risk operation uses the same
        account lookup.
        """

        account = await self.trading_account_repository.get_by_id(account_id)

        if not account:
            raise InvalidRiskConfiguration(
                f"Trading account {account_id} does not exist"
            )

        return account

    # ==========================================================
    # LOAD SYMBOL
    # ==========================================================

    async def _get_symbol(
        self,
        symbol_id: UUID,
    ):
        """
        Load symbol metadata from the database.
        """

        symbol = await self.symbol_repository.get_by_id(symbol_id)

        if not symbol:
            raise InvalidRiskConfiguration(f"Symbol {symbol_id} does not exist")

        if not symbol.active:
            raise InvalidRiskConfiguration(f"Symbol {symbol_id} is not active")

        return symbol

    # ==========================================================
    # BUILD SERVER-SIDE RISK STATE
    # ==========================================================

    async def build_risk_state(
        self,
        account_id: UUID,
        symbol_id: UUID | None = None,
        strategy: str | None = None,
    ) -> RiskState:

        # ------------------------------------------------------
        # 1. Load account
        # ------------------------------------------------------

        account = await self._get_account(account_id)

        # ------------------------------------------------------
        # 2. Load open positions
        # ------------------------------------------------------

        positions = await self.position_repository.get_by_account(account_id)

        open_positions = [
            position for position in positions if position.status == PositionStatus.OPEN
        ]

        # ------------------------------------------------------
        # 3. Aggregate position volume
        # ------------------------------------------------------

        total_volume = Decimal("0")

        for position in open_positions:

            current_volume = (
                position.current_volume
                if position.current_volume is not None
                else position.volume
            )

            total_volume += current_volume

        # ------------------------------------------------------
        # 4. Aggregate open risk
        # ------------------------------------------------------

        total_open_risk = Decimal("0")

        for position in open_positions:

            if position.initial_risk is not None:
                total_open_risk += position.initial_risk

        # ------------------------------------------------------
        # 5. Aggregate floating P/L
        # ------------------------------------------------------

        floating_profit_loss = Decimal("0")

        for position in open_positions:

            if position.floating_profit is not None:
                floating_profit_loss += position.floating_profit

        # ------------------------------------------------------
        # 6. Exposure
        # ------------------------------------------------------
        #
        # At this stage we use:
        #
        #       current_price × current_volume
        #
        # Later, this should be upgraded to use the symbol's
        # contract size / broker-specific notional calculation.
        #
        # We deliberately keep this calculation here rather than
        # putting it inside RiskCalculator because RiskCalculator
        # must remain a pure mathematical component.
        # ------------------------------------------------------

        total_exposure = Decimal("0")
        symbol_exposure_amount = Decimal("0")
        strategy_exposure_amount = Decimal("0")

        for position in open_positions:

            current_volume = (
                position.current_volume
                if position.current_volume is not None
                else position.volume
            )

            current_price = position.current_price

            if current_volume is not None and current_price is not None:
                exposure = current_volume * current_price
                total_exposure += exposure

                if symbol_id is not None and position.symbol_id == symbol_id:
                    symbol_exposure_amount += exposure

                if strategy is not None and position.strategy == strategy:
                    strategy_exposure_amount += exposure

        # ------------------------------------------------------
        # 7. Daily loss
        # ------------------------------------------------------
        #
        # At this stage the account model does not appear to have
        # a dedicated daily-start-equity field.
        #
        # Therefore we do NOT fabricate a daily loss number.
        #
        # The current floating loss is used as the temporary
        # server-side risk signal.
        #
        # Once RiskSnapshot/history is implemented, this will be
        # replaced by:
        #
        #     start_of_day_equity - current_equity
        #
        # ------------------------------------------------------

        daily_loss_amount = Decimal("0")

        if floating_profit_loss < 0:
            daily_loss_amount = abs(floating_profit_loss)

        # ------------------------------------------------------
        # 8. Drawdown
        # ------------------------------------------------------
        #
        # True drawdown requires an equity high-water mark.
        #
        # That will be introduced with RiskSnapshot / account
        # equity history.
        #
        # For now, we use zero rather than pretending floating
        # loss is historical drawdown.
        # ------------------------------------------------------

        drawdown_amount = Decimal("0")

        # ------------------------------------------------------
        # 9. Return server-side state
        # ------------------------------------------------------

        return RiskState(
            account_id=account.id,
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.free_margin,
            margin_level=account.margin_level,
            open_positions=len(open_positions),
            total_volume=total_volume,
            total_open_risk=total_open_risk,
            total_exposure=total_exposure,
            floating_profit_loss=floating_profit_loss,
            daily_loss_amount=daily_loss_amount,
            drawdown_amount=drawdown_amount,
            symbol_exposure_amount=symbol_exposure_amount,
            strategy_exposure_amount=strategy_exposure_amount,
        )

    # ==========================================================
    # EFFECTIVE RISK
    # ==========================================================

    async def get_effective_risk_percent(
        self,
        account_id: UUID,
    ) -> Decimal:

        profile = await self.risk_repository.get_by_account(account_id)

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account " f"{account_id}"
            )

        if not profile.enabled:
            raise InvalidRiskConfiguration(
                "Risk management is disabled for this account"
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
    ) -> RiskSizingResponse:

        # ------------------------------------------------------
        # 1. Load account server-side
        # ------------------------------------------------------

        account = await self._get_account(data.account_id)

        # ------------------------------------------------------
        # 2. Load symbol server-side
        # ------------------------------------------------------

        symbol = await self._get_symbol(data.symbol_id)

        # ------------------------------------------------------
        # 3. Load risk profile
        # ------------------------------------------------------

        profile = await self.risk_repository.get_by_account(data.account_id)

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account " f"{data.account_id}"
            )

        if not profile.enabled:
            raise InvalidRiskConfiguration(
                "Risk management is disabled for this account"
            )

        # ------------------------------------------------------
        # 4. Effective risk
        # ------------------------------------------------------

        risk_percent = RiskCalculator.effective_risk_percent(
            base_risk_percent=profile.base_risk_percent,
            risk_multiplier=profile.risk_multiplier,
            min_risk_percent=profile.min_risk_percent,
            max_risk_percent=profile.max_risk_percent,
        )

        # ------------------------------------------------------
        # 5. Account risk amount
        # ------------------------------------------------------

        risk_amount = RiskCalculator.risk_amount(
            equity=account.equity,
            risk_percent=risk_percent,
        )

        # ------------------------------------------------------
        # 6. Stop distance
        # ------------------------------------------------------

        stop_distance = RiskCalculator.stop_distance(
            entry_price=data.entry_price,
            stop_loss_price=data.stop_loss_price,
        )

        # ------------------------------------------------------
        # 7. Tick information
        # ------------------------------------------------------
        #
        # Symbol metadata is now loaded server-side.
        #
        # We prefer the database symbol values.
        #
        # The request should not be trusted to override broker
        # symbol specifications.
        # ------------------------------------------------------

        tick_size = symbol.tick_size

        tick_value = symbol.tick_value

        if tick_size <= 0:
            raise InvalidRiskConfiguration(
                f"Symbol {symbol.name} has an invalid tick size"
            )

        if tick_value <= 0:
            raise InvalidRiskConfiguration(
                f"Symbol {symbol.name} has an invalid tick value"
            )

        # ------------------------------------------------------
        # 8. Risk per unit
        # ------------------------------------------------------

        risk_per_unit = RiskCalculator.risk_per_unit(
            stop_distance=stop_distance,
            tick_size=tick_size,
            tick_value=tick_value,
        )

        # ------------------------------------------------------
        # 9. Raw volume
        # ------------------------------------------------------

        raw_volume = risk_amount / risk_per_unit

        # ------------------------------------------------------
        # 10. Recommended volume
        # ------------------------------------------------------

        recommended_volume = RiskCalculator.position_size(
            risk_amount=risk_amount,
            risk_per_unit=risk_per_unit,
            volume_step=symbol.volume_step,
        )

        # ------------------------------------------------------
        # 11. Broker volume limits
        # ------------------------------------------------------

        if recommended_volume < symbol.min_volume:
            raise InvalidRiskConfiguration(
                "Calculated position size is below the symbol " "minimum volume"
            )

        if recommended_volume > symbol.max_volume:
            raise InvalidRiskConfiguration(
                "Calculated position size exceeds the symbol " "maximum volume"
            )

        return RiskSizingResponse(
            account_id=data.account_id,
            symbol_id=data.symbol_id,
            risk_percent=risk_percent,
            risk_multiplier=profile.risk_multiplier,
            equity=account.equity,
            risk_amount=risk_amount,
            entry_price=data.entry_price,
            stop_loss_price=data.stop_loss_price,
            stop_distance=stop_distance,
            tick_size=tick_size,
            tick_value=tick_value,
            risk_per_unit=risk_per_unit,
            raw_volume=raw_volume.quantize(Decimal("0.00000001")),
            recommended_volume=recommended_volume,
            volume_step=symbol.volume_step,
            minimum_volume=symbol.min_volume,
            maximum_volume=symbol.max_volume,
        )

    # ==========================================================
    # SERVER-SIDE RISK CHECK
    # ==========================================================

    async def check_trade(
        self,
        data: RiskCheckRequest,
    ) -> RiskCheckResponse:

        # ------------------------------------------------------
        # 1. Load account
        # ------------------------------------------------------

        account = await self._get_account(data.account_id)

        # ------------------------------------------------------
        # 2. Load risk profile
        # ------------------------------------------------------

        profile = await self.risk_repository.get_by_account(data.account_id)

        if not profile:
            raise RiskProfileNotFound(
                f"No risk profile exists for account " f"{data.account_id}"
            )

        if not profile.enabled:
            raise InvalidRiskConfiguration(
                "Risk management is disabled for this account"
            )

        # ------------------------------------------------------
        # 3. Build server-side risk state
        # ------------------------------------------------------

        state = await self.build_risk_state(
            data.account_id,
            symbol_id=data.symbol_id,
            strategy=data.strategy,
        )

        # ------------------------------------------------------
        # 4. Determine proposed risk
        # ------------------------------------------------------
        #
        # The proposed trade risk amount may still come from the
        # position-sizing calculation.
        #
        # However, current account state MUST come from the
        # server-side RiskState.
        # ------------------------------------------------------

        proposed_risk_amount = data.proposed_risk_amount

        proposed_symbol_exposure_amount = data.proposed_symbol_exposure_amount

        proposed_strategy_exposure_amount = data.proposed_strategy_exposure_amount

        # ------------------------------------------------------
        # 5. Risk rules
        # ------------------------------------------------------

        rules = RiskRules(profile)

        decision = rules.check(
            state=state,
            proposed_risk_amount=proposed_risk_amount,
            proposed_symbol_exposure_amount=proposed_symbol_exposure_amount,
            proposed_strategy_exposure_amount=proposed_strategy_exposure_amount,
        )

        projected_open_risk = state.total_open_risk + proposed_risk_amount

        return RiskCheckResponse(
            account_id=data.account_id,
            symbol_id=data.symbol_id,
            approved=decision.approved,
            code=decision.code,
            message=decision.message,
            risk_percent=rules.effective_risk_percent(),
            proposed_risk_amount=proposed_risk_amount,
            current_open_risk=state.total_open_risk,
            projected_open_risk=projected_open_risk,
            current_open_positions=state.open_positions,
            projected_open_positions=state.open_positions + 1,
            trading_halted=decision.rejected,
            metadata=decision.metadata,
        )
