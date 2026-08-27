"""Shared enumerations for the Athena Quant Engine.

This module contains common enum definitions used across AQE
subsystems. Enums provide standardized values and prevent different
components from using inconsistent string representations.
"""

from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    """Runtime environment."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class TradingMode(StrEnum):
    """Trading execution mode."""

    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class BrokerType(StrEnum):
    """Supported broker types."""

    PAPER = "paper"
    MT5 = "mt5"
    BINANCE = "binance"
    FIX = "fix"


class AssetClass(StrEnum):
    """Supported financial asset classes."""

    FOREX = "forex"
    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    FUTURES = "futures"
    OPTIONS = "options"
    CFD = "cfd"
    INDEX = "index"
    COMMODITY = "commodity"


class OrderSide(StrEnum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class PositionSide(StrEnum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


class OrderType(StrEnum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    """Order time-in-force policies."""

    GTC = "gtc"
    GTD = "gtd"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"


class OrderStatus(StrEnum):
    """Order lifecycle status."""

    CREATED = "created"
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class PositionStatus(StrEnum):
    """Position lifecycle status."""

    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"


class SignalType(StrEnum):
    """Trading signal direction."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class SignalStrength(StrEnum):
    """Qualitative signal strength."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class StrategyStatus(StrEnum):
    """Strategy lifecycle status."""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class RiskDecision(StrEnum):
    """Risk-engine decision."""

    APPROVE = "approve"
    REJECT = "reject"
    REDUCE = "reduce"


class RiskLevel(StrEnum):
    """Risk severity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MarketSession(StrEnum):
    """Major FX/financial-market sessions."""

    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    CLOSED = "closed"


class Timeframe(StrEnum):
    """Common market-data timeframes."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1mo"


class TradeStatus(StrEnum):
    """Trade lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class BacktestStatus(StrEnum):
    """Backtest lifecycle status."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(StrEnum):
    """Machine-learning model lifecycle status."""

    CREATED = "created"
    TRAINING = "training"
    READY = "ready"
    DEPLOYED = "deployed"
    RETIRED = "retired"
    FAILED = "failed"


class HealthStatus(StrEnum):
    """System health state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentStatus(StrEnum):
    """Generic AQE component lifecycle state."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


__all__ = [
    "AssetClass",
    "BacktestStatus",
    "BrokerType",
    "ComponentStatus",
    "Environment",
    "HealthStatus",
    "MarketSession",
    "ModelStatus",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PositionSide",
    "PositionStatus",
    "RiskDecision",
    "RiskLevel",
    "SignalStrength",
    "SignalType",
    "StrategyStatus",
    "TimeInForce",
    "Timeframe",
    "TradeStatus",
    "TradingMode",
]
