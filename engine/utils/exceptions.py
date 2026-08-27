"""Exception hierarchy for the Athena Quant Engine.

All engine-specific exceptions inherit from AQEError. This provides a
consistent error-handling interface across market data, strategies,
risk management, execution, brokers, portfolio management, analytics,
backtesting, and infrastructure.
"""

from __future__ import annotations

from typing import Any


class AQEError(Exception):
    """Base exception for all Athena Quant Engine errors."""

    code = "AQE_ERROR"

    def __init__(
        self,
        message: str = "An Athena Quant Engine error occurred.",
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.code = code or self.code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Return a structured representation of the exception."""

        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        """Return the human-readable error message."""

        return self.message


# ============================================================================
# Configuration
# ============================================================================


class ConfigurationError(AQEError):
    """Base error for configuration problems."""

    code = "CONFIGURATION_ERROR"


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration values are invalid."""

    code = "INVALID_CONFIGURATION"


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration is missing."""

    code = "MISSING_CONFIGURATION"


# ============================================================================
# Lifecycle / Engine
# ============================================================================


class EngineError(AQEError):
    """Base error for engine lifecycle and orchestration problems."""

    code = "ENGINE_ERROR"


class EngineNotInitializedError(EngineError):
    """Raised when an engine component is used before initialization."""

    code = "ENGINE_NOT_INITIALIZED"


class EngineAlreadyRunningError(EngineError):
    """Raised when attempting to start an already-running engine."""

    code = "ENGINE_ALREADY_RUNNING"


class EngineNotRunningError(EngineError):
    """Raised when an operation requires a running engine."""

    code = "ENGINE_NOT_RUNNING"


class EngineShutdownError(EngineError):
    """Raised when the engine cannot shut down cleanly."""

    code = "ENGINE_SHUTDOWN_ERROR"


# ============================================================================
# Event System
# ============================================================================


class EventError(AQEError):
    """Base error for the AQE event system."""

    code = "EVENT_ERROR"


class EventBusError(EventError):
    """Base error for event-bus failures."""

    code = "EVENT_BUS_ERROR"


class EventBusClosedError(EventBusError):
    """Raised when attempting to use a closed event bus."""

    code = "EVENT_BUS_CLOSED"


class EventPublishError(EventError):
    """Raised when an event cannot be published."""

    code = "EVENT_PUBLISH_ERROR"


class EventSubscriptionError(EventError):
    """Raised when event subscription fails."""

    code = "EVENT_SUBSCRIPTION_ERROR"


# ============================================================================
# Market Data
# ============================================================================


class MarketError(AQEError):
    """Base error for market-data operations."""

    code = "MARKET_ERROR"


class MarketDataError(MarketError):
    """Raised when market data cannot be obtained or processed."""

    code = "MARKET_DATA_ERROR"


class MarketDataUnavailableError(MarketDataError):
    """Raised when required market data is unavailable."""

    code = "MARKET_DATA_UNAVAILABLE"


class InvalidMarketDataError(MarketDataError):
    """Raised when market data fails validation."""

    code = "INVALID_MARKET_DATA"


class SymbolError(MarketError):
    """Base error for symbol-related operations."""

    code = "SYMBOL_ERROR"


class UnknownSymbolError(SymbolError):
    """Raised when a requested symbol is not known."""

    code = "UNKNOWN_SYMBOL"


class InactiveSymbolError(SymbolError):
    """Raised when attempting to trade an inactive symbol."""

    code = "INACTIVE_SYMBOL"


# ============================================================================
# Strategy
# ============================================================================


class StrategyError(AQEError):
    """Base error for strategy operations."""

    code = "STRATEGY_ERROR"


class StrategyNotFoundError(StrategyError):
    """Raised when a strategy cannot be found."""

    code = "STRATEGY_NOT_FOUND"


class StrategyAlreadyRegisteredError(StrategyError):
    """Raised when registering an already registered strategy."""

    code = "STRATEGY_ALREADY_REGISTERED"


class StrategyNotRunningError(StrategyError):
    """Raised when a strategy operation requires a running strategy."""

    code = "STRATEGY_NOT_RUNNING"


class StrategyExecutionError(StrategyError):
    """Raised when strategy execution fails."""

    code = "STRATEGY_EXECUTION_ERROR"


class InvalidSignalError(StrategyError):
    """Raised when a generated trading signal is invalid."""

    code = "INVALID_SIGNAL"


# ============================================================================
# Risk
# ============================================================================


class RiskError(AQEError):
    """Base error for risk-management operations."""

    code = "RISK_ERROR"


class RiskViolationError(RiskError):
    """Raised when a proposed action violates a risk rule."""

    code = "RISK_VIOLATION"


class RiskLimitExceededError(RiskError):
    """Raised when a configured risk limit is exceeded."""

    code = "RISK_LIMIT_EXCEEDED"


class DrawdownLimitExceededError(RiskError):
    """Raised when the drawdown limit is exceeded."""

    code = "DRAWDOWN_LIMIT_EXCEEDED"


class ExposureLimitExceededError(RiskError):
    """Raised when an exposure limit is exceeded."""

    code = "EXPOSURE_LIMIT_EXCEEDED"


class PositionSizeError(RiskError):
    """Raised when a position size is invalid or unsafe."""

    code = "POSITION_SIZE_ERROR"


class MarginError(RiskError):
    """Raised when margin requirements cannot be satisfied."""

    code = "MARGIN_ERROR"


class CorrelationLimitError(RiskError):
    """Raised when portfolio correlation risk exceeds limits."""

    code = "CORRELATION_LIMIT_EXCEEDED"


# ============================================================================
# Orders
# ============================================================================


class OrderError(AQEError):
    """Base error for order operations."""

    code = "ORDER_ERROR"


class InvalidOrderError(OrderError):
    """Raised when an order fails validation."""

    code = "INVALID_ORDER"


class OrderRejectedError(OrderError):
    """Raised when an order is rejected."""

    code = "ORDER_REJECTED"


class OrderNotFoundError(OrderError):
    """Raised when an order cannot be found."""

    code = "ORDER_NOT_FOUND"


class OrderAlreadyFilledError(OrderError):
    """Raised when modifying an already-filled order."""

    code = "ORDER_ALREADY_FILLED"


class OrderCancellationError(OrderError):
    """Raised when an order cannot be cancelled."""

    code = "ORDER_CANCELLATION_ERROR"


# ============================================================================
# Execution
# ============================================================================


class ExecutionError(AQEError):
    """Base error for trade execution."""

    code = "EXECUTION_ERROR"


class ExecutionRejectedError(ExecutionError):
    """Raised when execution is rejected."""

    code = "EXECUTION_REJECTED"


class ExecutionTimeoutError(ExecutionError):
    """Raised when execution times out."""

    code = "EXECUTION_TIMEOUT"


class ExecutionUnavailableError(ExecutionError):
    """Raised when execution infrastructure is unavailable."""

    code = "EXECUTION_UNAVAILABLE"


class PartialExecutionError(ExecutionError):
    """Raised when an execution is only partially completed."""

    code = "PARTIAL_EXECUTION"


# ============================================================================
# Broker
# ============================================================================


class BrokerError(AQEError):
    """Base error for broker operations."""

    code = "BROKER_ERROR"


class BrokerConnectionError(BrokerError):
    """Raised when connection to a broker fails."""

    code = "BROKER_CONNECTION_ERROR"


class BrokerAuthenticationError(BrokerError):
    """Raised when broker authentication fails."""

    code = "BROKER_AUTHENTICATION_ERROR"


class BrokerUnavailableError(BrokerError):
    """Raised when a broker is unavailable."""

    code = "BROKER_UNAVAILABLE"


class BrokerOrderError(BrokerError):
    """Raised when a broker rejects or fails an order."""

    code = "BROKER_ORDER_ERROR"


class BrokerRateLimitError(BrokerError):
    """Raised when broker API rate limits are exceeded."""

    code = "BROKER_RATE_LIMIT"


# ============================================================================
# Portfolio
# ============================================================================


class PortfolioError(AQEError):
    """Base error for portfolio operations."""

    code = "PORTFOLIO_ERROR"


class AccountError(PortfolioError):
    """Raised for account-state errors."""

    code = "ACCOUNT_ERROR"


class PositionError(PortfolioError):
    """Raised for position-state errors."""

    code = "POSITION_ERROR"


class PositionNotFoundError(PositionError):
    """Raised when a requested position does not exist."""

    code = "POSITION_NOT_FOUND"


class InvalidPositionError(PositionError):
    """Raised when a position operation is invalid."""

    code = "INVALID_POSITION"


# ============================================================================
# Database
# ============================================================================


class DatabaseError(AQEError):
    """Base error for database operations."""

    code = "DATABASE_ERROR"


class DatabaseConnectionError(DatabaseError):
    """Raised when the database cannot be reached."""

    code = "DATABASE_CONNECTION_ERROR"


class DatabaseQueryError(DatabaseError):
    """Raised when a database query fails."""

    code = "DATABASE_QUERY_ERROR"


class DatabaseIntegrityError(DatabaseError):
    """Raised when database integrity constraints are violated."""

    code = "DATABASE_INTEGRITY_ERROR"


class RecordNotFoundError(DatabaseError):
    """Raised when a requested database record does not exist."""

    code = "RECORD_NOT_FOUND"


# ============================================================================
# Backtesting
# ============================================================================


class BacktestError(AQEError):
    """Base error for backtesting operations."""

    code = "BACKTEST_ERROR"


class BacktestConfigurationError(BacktestError):
    """Raised when backtest configuration is invalid."""

    code = "BACKTEST_CONFIGURATION_ERROR"


class BacktestDataError(BacktestError):
    """Raised when backtest data is invalid or unavailable."""

    code = "BACKTEST_DATA_ERROR"


class BacktestExecutionError(BacktestError):
    """Raised when backtest execution fails."""

    code = "BACKTEST_EXECUTION_ERROR"


# ============================================================================
# Analytics
# ============================================================================


class AnalyticsError(AQEError):
    """Base error for analytics operations."""

    code = "ANALYTICS_ERROR"


class InsufficientDataError(AnalyticsError):
    """Raised when there is insufficient data for a calculation."""

    code = "INSUFFICIENT_DATA"


class MetricCalculationError(AnalyticsError):
    """Raised when a metric cannot be calculated."""

    code = "METRIC_CALCULATION_ERROR"


# ============================================================================
# Machine Learning
# ============================================================================


class MLError(AQEError):
    """Base error for machine-learning operations."""

    code = "ML_ERROR"


class MLModelError(MLError):
    """Raised for machine-learning model failures."""

    code = "ML_MODEL_ERROR"


class MLModelNotFoundError(MLModelError):
    """Raised when a required ML model cannot be found."""

    code = "ML_MODEL_NOT_FOUND"


class MLModelNotReadyError(MLModelError):
    """Raised when a model is not ready for inference."""

    code = "ML_MODEL_NOT_READY"


class MLFeatureError(MLError):
    """Raised when ML features cannot be generated."""

    code = "ML_FEATURE_ERROR"


# ============================================================================
# Validation
# ============================================================================


class ValidationError(AQEError):
    """Base error for validation failures."""

    code = "VALIDATION_ERROR"


class RequiredFieldError(ValidationError):
    """Raised when a required field is missing."""

    code = "REQUIRED_FIELD"


class InvalidValueError(ValidationError):
    """Raised when a value fails validation."""

    code = "INVALID_VALUE"


class InvalidRangeError(ValidationError):
    """Raised when a numeric value is outside an allowed range."""

    code = "INVALID_RANGE"


# ============================================================================
# Monitoring
# ============================================================================


class MonitoringError(AQEError):
    """Base error for monitoring operations."""

    code = "MONITORING_ERROR"


class HealthCheckError(MonitoringError):
    """Raised when a health check fails."""

    code = "HEALTH_CHECK_ERROR"


class MetricsError(MonitoringError):
    """Raised when metrics collection fails."""

    code = "METRICS_ERROR"


__all__ = [
    # Base
    "AQEError",
    # Configuration
    "ConfigurationError",
    "InvalidConfigurationError",
    "MissingConfigurationError",
    # Engine
    "EngineError",
    "EngineNotInitializedError",
    "EngineAlreadyRunningError",
    "EngineNotRunningError",
    "EngineShutdownError",
    # Events
    "EventError",
    "EventBusError",
    "EventBusClosedError",
    "EventPublishError",
    "EventSubscriptionError",
    # Market
    "MarketError",
    "MarketDataError",
    "MarketDataUnavailableError",
    "InvalidMarketDataError",
    "SymbolError",
    "UnknownSymbolError",
    "InactiveSymbolError",
    # Strategy
    "StrategyError",
    "StrategyNotFoundError",
    "StrategyAlreadyRegisteredError",
    "StrategyNotRunningError",
    "StrategyExecutionError",
    "InvalidSignalError",
    # Risk
    "RiskError",
    "RiskViolationError",
    "RiskLimitExceededError",
    "DrawdownLimitExceededError",
    "ExposureLimitExceededError",
    "PositionSizeError",
    "MarginError",
    "CorrelationLimitError",
    # Orders
    "OrderError",
    "InvalidOrderError",
    "OrderRejectedError",
    "OrderNotFoundError",
    "OrderAlreadyFilledError",
    "OrderCancellationError",
    # Execution
    "ExecutionError",
    "ExecutionRejectedError",
    "ExecutionTimeoutError",
    "ExecutionUnavailableError",
    "PartialExecutionError",
    # Broker
    "BrokerError",
    "BrokerConnectionError",
    "BrokerAuthenticationError",
    "BrokerUnavailableError",
    "BrokerOrderError",
    "BrokerRateLimitError",
    # Portfolio
    "PortfolioError",
    "AccountError",
    "PositionError",
    "PositionNotFoundError",
    "InvalidPositionError",
    # Database
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseQueryError",
    "DatabaseIntegrityError",
    "RecordNotFoundError",
    # Backtesting
    "BacktestError",
    "BacktestConfigurationError",
    "BacktestDataError",
    "BacktestExecutionError",
    # Analytics
    "AnalyticsError",
    "InsufficientDataError",
    "MetricCalculationError",
    # ML
    "MLError",
    "MLModelError",
    "MLModelNotFoundError",
    "MLModelNotReadyError",
    "MLFeatureError",
    # Validation
    "ValidationError",
    "RequiredFieldError",
    "InvalidValueError",
    "InvalidRangeError",
    # Monitoring
    "MonitoringError",
    "HealthCheckError",
    "MetricsError",
]
