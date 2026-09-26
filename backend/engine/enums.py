from __future__ import annotations

from enum import Enum


class EngineMode(str, Enum):
    """
    Operating mode of the AQE runtime.

    LIVE
        Real broker execution.

    PAPER
        Paper/simulated broker execution.

    BACKTEST
        Historical simulation.

    REPLAY
        Historical/event replay without normal live execution.
    """

    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"


class EngineStatus(str, Enum):
    """Top-level AQE Engine lifecycle state."""

    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"

    PAUSING = "PAUSING"
    PAUSED = "PAUSED"

    RESUMING = "RESUMING"

    STOPPING = "STOPPING"
    STOPPED = "STOPPED"

    ERROR = "ERROR"