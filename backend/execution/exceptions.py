from __future__ import annotations


class ExecutionError(Exception):
    """Base exception for execution-engine failures."""


class ExecutionValidationError(ExecutionError):
    """Raised when an execution request cannot be built safely."""


class ExecutionRejectedError(ExecutionError):
    """Raised when execution is attempted with a rejected risk decision."""


class ExecutionBrokerError(ExecutionError):
    """Raised when the broker fails to execute an approved order."""