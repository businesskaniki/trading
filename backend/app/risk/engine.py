"""Risk engine public facade."""

from app.risk.calculator import RiskCalculator
from app.risk.decision import RiskDecision


class RiskEngine:
    """Lightweight facade for risk calculations and decisions."""

    calculator = RiskCalculator
    decision = RiskDecision
