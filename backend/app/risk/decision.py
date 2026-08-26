from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskDecisionStatus(str, Enum):
    """
    Result status produced by the Risk Engine.
    """

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiskDecision:
    """
    Immutable result of a Risk Engine rule evaluation.

    A RiskDecision is deliberately separate from HTTP responses,
    database models, and broker objects.

    The Risk Engine can therefore be used by:
        - REST API
        - Order Engine
        - Execution Engine
        - Strategy Engine
        - Backtesting Engine
        - Automated trading workers
    """

    status: RiskDecisionStatus
    code: str
    message: str
    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    # ==========================================================
    # FACTORY METHODS
    # ==========================================================

    @classmethod
    def approve(
        cls,
        *,
        code: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> "RiskDecision":
        """
        Create an approved risk decision.
        """

        return cls(
            status=RiskDecisionStatus.APPROVED,
            code=code,
            message=message,
            metadata=metadata or {},
        )

    @classmethod
    def reject(
        cls,
        *,
        code: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> "RiskDecision":
        """
        Create a rejected risk decision.
        """

        return cls(
            status=RiskDecisionStatus.REJECTED,
            code=code,
            message=message,
            metadata=metadata or {},
        )

    # ==========================================================
    # PROPERTIES
    # ==========================================================

    @property
    def approved(self) -> bool:
        """
        True when the risk decision allows the operation.
        """

        return self.status == RiskDecisionStatus.APPROVED

    @property
    def rejected(self) -> bool:
        """
        True when the risk decision rejects the operation.
        """

        return self.status == RiskDecisionStatus.REJECTED

    @property
    def is_approved(self) -> bool:
        """
        Alias for approved.

        Useful when reading service code naturally.
        """

        return self.approved

    @property
    def is_rejected(self) -> bool:
        """
        Alias for rejected.

        Useful when reading service code naturally.
        """

        return self.rejected

    # ==========================================================
    # SERIALIZATION
    # ==========================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the decision into a JSON-compatible structure.

        Decimal values inside metadata should normally be
        converted by the API serialization layer.
        """

        return {
            "status": self.status.value,
            "approved": self.approved,
            "code": self.code,
            "message": self.message,
            "metadata": self.metadata,
        }

    # ==========================================================
    # REPRESENTATION
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<RiskDecision("
            f"status={self.status.value}, "
            f"code={self.code}, "
            f"message={self.message!r})>"
        )
