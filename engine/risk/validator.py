"""Risk validation orchestration."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


class RiskValidator:
    def __init__(self, max_risk_percent: Decimal = Decimal("2")) -> None:
        self.max_risk_percent = max_risk_percent

    def validate_trade_risk(self, risk_percent: Decimal) -> RiskDecision:
        if risk_percent <= 0:
            return RiskDecision(False, "risk percent must be positive")
        if risk_percent > self.max_risk_percent:
            return RiskDecision(False, "risk percent exceeds maximum")
        return RiskDecision(True, "approved")
