class RiskError(Exception):
    """
    Base exception for all Risk Engine failures.
    """


# ==========================================================
# CONFIGURATION
# ==========================================================


class InvalidRiskConfiguration(RiskError):
    """
    Risk profile or risk configuration is invalid.
    """


class RiskProfileNotFound(RiskError):
    """
    No risk profile exists for the trading account.
    """


# ==========================================================
# CALCULATION
# ==========================================================


class RiskCalculationError(RiskError):
    """
    A mathematical risk calculation failed.
    """


# ==========================================================
# RISK LIMITS
# ==========================================================


class RiskLimitExceeded(RiskError):
    """
    A proposed trade violates one or more risk limits.
    """


class DailyLossLimitExceeded(RiskLimitExceeded):
    """
    Daily loss limit has been exceeded.
    """


class WeeklyLossLimitExceeded(RiskLimitExceeded):
    """
    Weekly loss limit has been exceeded.
    """


class DrawdownLimitExceeded(RiskLimitExceeded):
    """
    Maximum account drawdown has been exceeded.
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


# ==========================================================
# ACCOUNT / MARKET DATA
# ==========================================================


class TradingAccountNotFound(RiskError):
    """
    Trading account does not exist.
    """


class SymbolNotFound(RiskError):
    """
    Trading symbol does not exist.
    """


class AccountNotTradable(RiskError):
    """
    Trading account exists but is not currently tradable.
    """


class SymbolNotTradable(RiskError):
    """
    Symbol exists but is not currently active/tradable.
    """


# ==========================================================
# RISK STATE
# ==========================================================


class RiskStateError(RiskError):
    """
    Risk state could not be constructed or evaluated.
    """


class TradingHalted(RiskLimitExceeded):
    """
    Trading has been halted for the account because
    of a risk condition.
    """
