from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.database.models.trading_account import TradingAccount
from app.database.models.symbol import Symbol
from app.risk.models import RiskProfile


@dataclass(slots=True)
class RiskState:
    """
    Server-side snapshot of the current trading risk state.

    RiskState is NOT a database model.

    It represents the authoritative state used by the
    Risk Engine when making risk decisions.

    All values are assembled server-side from trusted
    database/domain sources.
    """

    # ==========================================================
    # IDENTIFICATION
    # ==========================================================

    account_id: UUID

    # ==========================================================
    # ACCOUNT STATE
    # ==========================================================

    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal

    # ==========================================================
    # RISK PROFILE
    # ==========================================================

    risk_profile_id: UUID
    risk_enabled: bool

    base_risk_percent: Decimal
    risk_multiplier: Decimal
    min_risk_percent: Decimal
    max_risk_percent: Decimal

    max_daily_loss_percent: Decimal
    max_drawdown_percent: Decimal
    max_open_risk_percent: Decimal

    # ==========================================================
    # CURRENT EXPOSURE
    # ==========================================================

    open_positions: int
    open_orders: int

    total_volume: Decimal
    total_exposure: Decimal

    # ==========================================================
    # CURRENT OPEN RISK
    # ==========================================================

    total_open_risk: Decimal

    # ==========================================================
    # LOSS / DRAWDOWN
    # ==========================================================

    daily_loss: Decimal
    daily_loss_percent: Decimal

    drawdown: Decimal
    drawdown_percent: Decimal

    # ==========================================================
    # RISK FLAGS
    # ==========================================================

    trading_halted: bool

    daily_loss_limit_hit: bool
    drawdown_limit_hit: bool

    # ==========================================================
    # DERIVED VALUES
    # ==========================================================

    @property
    def effective_risk_percent(self) -> Decimal:
        """
        Effective risk percentage after applying the
        account risk multiplier and configured bounds.

        This is calculated by the RiskCalculator rather
        than duplicated here.
        """

        from app.risk.calculator import RiskCalculator

        return RiskCalculator.effective_risk_percent(
            base_risk_percent=self.base_risk_percent,
            risk_multiplier=self.risk_multiplier,
            min_risk_percent=self.min_risk_percent,
            max_risk_percent=self.max_risk_percent,
        )

    @property
    def effective_risk_amount(self) -> Decimal:
        """
        Maximum risk amount permitted for the next trade
        before aggregate risk limits are considered.
        """

        from app.risk.calculator import RiskCalculator

        return RiskCalculator.risk_amount(
            equity=self.equity,
            risk_percent=self.effective_risk_percent,
        )


@dataclass(slots=True)
class SymbolRiskState:
    """
    Server-side risk information for a particular symbol.

    This is useful when the Risk Engine evaluates symbol
    exposure limits.
    """

    symbol_id: UUID
    symbol_name: str

    total_volume: Decimal
    exposure: Decimal
    open_positions: int
    open_orders: int


class RiskStateBuilder:
    """
    Builds authoritative server-side RiskState.

    This class is responsible for assembling risk information
    from domain objects.

    It does NOT:
        - execute trades
        - place orders
        - modify positions
        - perform HTTP operations
        - make final risk decisions

    Its responsibility is state construction only.
    """

    @staticmethod
    def from_account(
        account: TradingAccount,
        profile: RiskProfile,
        *,
        open_positions: int = 0,
        open_orders: int = 0,
        total_volume: Decimal = Decimal("0"),
        total_exposure: Decimal = Decimal("0"),
        total_open_risk: Decimal = Decimal("0"),
        daily_loss: Decimal = Decimal("0"),
        daily_loss_percent: Decimal = Decimal("0"),
        drawdown: Decimal = Decimal("0"),
        drawdown_percent: Decimal = Decimal("0"),
        trading_halted: bool = False,
        daily_loss_limit_hit: bool = False,
        drawdown_limit_hit: bool = False,
    ) -> RiskState:
        """
        Build a RiskState from a TradingAccount and RiskProfile.

        The exposure and position-related values are supplied
        by the server-side state collector.

        They should never come directly from an HTTP request.
        """

        return RiskState(
            # --------------------------------------------------
            # Identification
            # --------------------------------------------------
            account_id=account.id,
            # --------------------------------------------------
            # Account state
            # --------------------------------------------------
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.free_margin,
            margin_level=account.margin_level,
            # --------------------------------------------------
            # Risk profile
            # --------------------------------------------------
            risk_profile_id=profile.id,
            risk_enabled=profile.enabled,
            base_risk_percent=profile.base_risk_percent,
            risk_multiplier=profile.risk_multiplier,
            min_risk_percent=profile.min_risk_percent,
            max_risk_percent=profile.max_risk_percent,
            max_daily_loss_percent=(profile.max_daily_loss_percent),
            max_drawdown_percent=(profile.max_drawdown_percent),
            max_open_risk_percent=(profile.max_open_risk_percent),
            # --------------------------------------------------
            # Exposure
            # --------------------------------------------------
            open_positions=open_positions,
            open_orders=open_orders,
            total_volume=total_volume,
            total_exposure=total_exposure,
            # --------------------------------------------------
            # Open risk
            # --------------------------------------------------
            total_open_risk=total_open_risk,
            # --------------------------------------------------
            # Loss / drawdown
            # --------------------------------------------------
            daily_loss=daily_loss,
            daily_loss_percent=daily_loss_percent,
            drawdown=drawdown,
            drawdown_percent=drawdown_percent,
            # --------------------------------------------------
            # Risk flags
            # --------------------------------------------------
            trading_halted=trading_halted,
            daily_loss_limit_hit=(daily_loss_limit_hit),
            drawdown_limit_hit=(drawdown_limit_hit),
        )
