class RiskError(Exception):
    """
    Base exception for Risk Engine failures.
    """


class InvalidRiskConfiguration(RiskError):
    """
    Risk configuration is invalid.
    """


class RiskLimitExceeded(RiskError):
    """
    Proposed trade violates a risk limit.
    """


class DailyLossLimitExceeded(RiskLimitExceeded):
    """
    Daily loss limit has been exceeded.
    """


class DrawdownLimitExceeded(RiskLimitExceeded):
    """
    Maximum drawdown limit has been exceeded.
    """


class OpenRiskLimitExceeded(RiskLimitExceeded):
    """
    Aggregate open-risk limit has been exceeded.
    """


class PositionLimitExceeded(RiskLimitExceeded):
    """
    Maximum number of open positions has been exceeded.
    """


class SymbolExposureLimitExceeded(RiskLimitExceeded):
    """
    Symbol exposure limit has been exceeded.
    """


class StrategyExposureLimitExceeded(RiskLimitExceeded):
    """
    Strategy exposure limit has been exceeded.
    """


class RiskProfileNotFound(RiskError):
    """
    No risk profile exists for the trading account.
    """


class RiskCalculationError(RiskError):
    """
    Position sizing calculation failed.
    """