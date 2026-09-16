"""Base contracts for AQE Risk Engine rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..enums import RiskRejectionReason
from ..models import RiskContext


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Result returned by a Risk Engine rule."""

    passed: bool
    reason: RiskRejectionReason | None = None
    message: str | None = None

    @classmethod
    def pass_(cls) -> "RuleResult":
        """Create a successful rule result."""
        return cls(passed=True)

    @classmethod
    def reject(
        cls,
        reason: RiskRejectionReason,
        message: str,
    ) -> "RuleResult":
        """Create a failed rule result."""
        return cls(
            passed=False,
            reason=reason,
            message=message,
        )


T = TypeVar("T")


class RiskRule(ABC, Generic[T]):
    """Abstract base class for a Risk Engine rule."""

    name: str = "risk_rule"

    @abstractmethod
    def evaluate(self, context: RiskContext) -> RuleResult:
        """
        Evaluate the rule against the current risk context.

        Rules must not mutate the supplied context.
        """
        raise NotImplementedError