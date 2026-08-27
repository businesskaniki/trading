"""Core constants for the Athena Quant Engine.

This module contains values shared across the engine runtime.
Keep this module dependency-light: it must not import broker,
database, strategy, risk, or application modules.
"""

from __future__ import annotations

from enum import StrEnum


class EngineState(StrEnum):
    """Runtime states of the Athena Quant Engine."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class TradingMode(StrEnum):
    """Execution modes supported by the engine."""

    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class OrderSide(StrEnum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    """Order time-in-force policies."""

    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class PositionSide(StrEnum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


class Environment(StrEnum):
    """Application runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# Engine-level defaults.
DEFAULT_TRADING_MODE = TradingMode.PAPER
DEFAULT_ENGINE_STATE = EngineState.CREATED
DEFAULT_ENVIRONMENT = Environment.DEVELOPMENT

# Safety defaults.
LIVE_TRADING_REQUIRES_EXPLICIT_ENABLE = True
PAPER_TRADING_ENABLED_BY_DEFAULT = True

# Trading loop defaults.
DEFAULT_TICK_INTERVAL_SECONDS = 1.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 30.0

# Risk-related defaults.
DEFAULT_MAX_POSITIONS = 10
DEFAULT_MAX_ORDERS_PER_SECOND = 10

# Numeric precision.
DEFAULT_PRICE_PRECISION = 8
DEFAULT_VOLUME_PRECISION = 8


__all__ = [
    "DEFAULT_ENVIRONMENT",
    "DEFAULT_ENGINE_STATE",
    "DEFAULT_HEARTBEAT_INTERVAL_SECONDS",
    "DEFAULT_MAX_ORDERS_PER_SECOND",
    "DEFAULT_MAX_POSITIONS",
    "DEFAULT_PRICE_PRECISION",
    "DEFAULT_SHUTDOWN_TIMEOUT_SECONDS",
    "DEFAULT_TICK_INTERVAL_SECONDS",
    "DEFAULT_TRADING_MODE",
    "DEFAULT_VOLUME_PRECISION",
    "Environment",
    "EngineState",
    "LIVE_TRADING_REQUIRES_EXPLICIT_ENABLE",
    "OrderSide",
    "OrderType",
    "PAPER_TRADING_ENABLED_BY_DEFAULT",
    "PositionSide",
    "TimeInForce",
    "TradingMode",
]