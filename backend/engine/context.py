from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import EngineConfig
from .enums import EngineMode, EngineStatus


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class EngineContext:
    """
    Runtime state owned by the AQE Engine.

    This object contains lifecycle information only.
    Trading business logic remains inside the respective subsystems.
    """

    config: EngineConfig

    status: EngineStatus = EngineStatus.CREATED

    created_at: datetime = field(default_factory=utc_now)

    started_at: datetime | None = None

    paused_at: datetime | None = None

    resumed_at: datetime | None = None

    stopped_at: datetime | None = None

    last_error: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> EngineMode:
        """Return the configured engine mode."""

        return self.config.mode

    @property
    def running(self) -> bool:
        """Return whether the engine is actively running."""

        return self.status is EngineStatus.RUNNING

    @property
    def paused(self) -> bool:
        """Return whether the engine is paused."""

        return self.status is EngineStatus.PAUSED

    def clear_error(self) -> None:
        """Clear the current engine error."""

        self.last_error = None

    def set_error(self, error: Exception | str) -> None:
        """Record an engine error."""

        self.last_error = str(error)