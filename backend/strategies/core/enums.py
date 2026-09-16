"""Enumerations used throughout the AQE Strategy Engine."""

from __future__ import annotations

from enum import StrEnum


class StrategyMode(StrEnum):
    """Execution mode in which a strategy instance operates."""

    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"
    REPLAY = "replay"


class StrategyStatus(StrEnum):
    """Lifecycle state of a strategy instance."""

    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class SignalDirection(StrEnum):
    """Directional intent of a trading signal."""

    LONG = "long"
    SHORT = "short"


class SignalType(StrEnum):
    """Trading action requested by a strategy."""

    ENTRY = "entry"
    EXIT = "exit"
    REDUCE = "reduce"
    REVERSE = "reverse"


class OrderType(StrEnum):
    """Order type requested by a trading signal."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class PriceType(StrEnum):
    """Market price used when evaluating or generating a signal."""

    BID = "bid"
    ASK = "ask"
    MID = "mid"


class PositionSide(StrEnum):
    """Side of an existing trading position."""

    LONG = "long"
    SHORT = "short"


class Timeframe(StrEnum):
    """
    Timeframes supported by the AQE Strategy Engine.

    TICK represents tick-level processing. The remaining values
    correspond to candle timeframes supported by AQE market data.
    """

    TICK = "TICK"

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"

    H1 = "H1"
    H4 = "H4"

    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class StrategyEventType(StrEnum):
    """Lifecycle and processing events produced by the Strategy Engine."""

    STARTED = "started"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESUMED = "resumed"

    MARKET_DATA = "market_data"
    SIGNAL_GENERATED = "signal_generated"

    ERROR = "error"
