
"""Exception hierarchy for the AQE Strategy Engine."""

from __future__ import annotations


class StrategyError(Exception):
    """Base exception for all Strategy Engine errors."""


class StrategyConfigurationError(StrategyError):
    """Raised when a strategy configuration is invalid."""


class StrategyInitializationError(StrategyError):
    """Raised when a strategy fails during initialization."""


class StrategyStateError(StrategyError):
    """Raised when an operation is invalid for the current strategy state."""


class StrategyNotFoundError(StrategyError):
    """Raised when a requested strategy is not registered."""


class StrategyAlreadyRegisteredError(StrategyError):
    """Raised when a strategy name is already registered."""


class StrategyExecutionError(StrategyError):
    """Raised when a strategy fails while processing market data."""


class InvalidMarketDataError(StrategyExecutionError):
    """Raised when market data cannot be processed by a strategy."""


class InvalidSignalError(StrategyError):
    """Raised when a strategy produces an invalid trading signal."""
