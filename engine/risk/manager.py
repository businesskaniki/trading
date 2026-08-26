"""Risk manager facade."""

from decimal import Decimal

from engine.risk.position_sizer import position_size
from engine.risk.validator import RiskDecision, RiskValidator


class RiskManager:
    def __init__(self, validator: RiskValidator | None = None) -> None:
        self.validator = validator or RiskValidator()

    def validate_trade_risk(self, risk_percent: Decimal) -> RiskDecision:
        return self.validator.validate_trade_risk(risk_percent)

    def size_position(self, **kwargs: Decimal) -> Decimal:
        return position_size(**kwargs)
