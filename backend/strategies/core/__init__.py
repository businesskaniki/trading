
"""Public API for the AQE Strategy Core."""

from .base import (
    BaseStrategy,
    StrategyConfig,
    StrategyDefinition,
)
from .context import (
    Clock,
    MarketDataView,
    PositionSnapshot,
    PositionView,
    StrategyContext,
    StrategyStateStore,
    SystemClock,
)
from .enums import (
    OrderType,
    PositionSide,
    PriceType,
    SignalDirection,
    SignalType,
    StrategyEventType,
    StrategyMode,
    StrategyStatus,
    Timeframe,
)
from .exceptions import (
    InvalidMarketDataError,
    InvalidSignalError,
    StrategyAlreadyRegisteredError,
    StrategyConfigurationError,
    StrategyError,
    StrategyExecutionError,
    StrategyInitializationError,
    StrategyNotFoundError,
    StrategyStateError,
)
from .registry import (
    StrategyRegistry,
    register_strategy,
    registry,
)
from .signal import TradingSignal

__all__ = [
    # Base
    "BaseStrategy",
    "StrategyConfig",
    "StrategyDefinition",

    # Context
    "Clock",
    "MarketDataView",
    "PositionSnapshot",
    "PositionView",
    "StrategyContext",
    "StrategyStateStore",
    "SystemClock",

    # Enums
    "OrderType",
    "PositionSide",
    "PriceType",
    "SignalDirection",
    "SignalType",
    "StrategyEventType",
    "StrategyMode",
    "StrategyStatus",
    "Timeframe",

    # Exceptions
    "InvalidMarketDataError",
    "InvalidSignalError",
    "StrategyAlreadyRegisteredError",
    "StrategyConfigurationError",
    "StrategyError",
    "StrategyExecutionError",
    "StrategyInitializationError",
    "StrategyNotFoundError",
    "StrategyStateError",

    # Registry
    "StrategyRegistry",
    "register_strategy",
    "registry",

    # Signals
    "TradingSignal",
]
