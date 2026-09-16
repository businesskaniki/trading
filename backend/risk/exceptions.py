"""Exceptions raised by the AQE Risk Engine."""

from __future__ import annotations


class RiskEngineError(Exception):
    """Base exception for Risk Engine failures."""


class RiskConfigurationError(RiskEngineError):
    """Raised when risk configuration is invalid."""


class RiskCalculationError(RiskEngineError):
    """Raised when a risk calculation cannot be completed."""


class RiskContextError(RiskEngineError):
    """Raised when required risk context is missing or invalid."""
