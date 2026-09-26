from __future__ import annotations


class EngineError(Exception):
    """Base exception for AQE Engine errors."""


class EngineStateError(EngineError):
    """Raised when an operation is invalid for the current engine state."""


class EngineStartupError(EngineError):
    """Raised when one or more engine components fail during startup."""


class EnginePauseError(EngineError):
    """Raised when the engine cannot be paused safely."""


class EngineResumeError(EngineError):
    """Raised when the engine cannot be resumed safely."""


class EngineShutdownError(EngineError):
    """Raised when one or more components fail during shutdown."""