"""Partial Close component implementation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PartialClose:
    """Configurable partial close component for the Athena engine."""

    enabled: bool = True
    settings: dict[str, Any] = field(default_factory=dict)

    def configure(self, **settings: Any) -> None:
        self.settings.update(settings)

    def run(self, **context: Any) -> dict[str, Any]:
        return {"component": "partial_close", "enabled": self.enabled, "settings": self.settings, "context": context}
