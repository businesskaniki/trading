"""Calendar component implementation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Calendar:
    """Configurable calendar component for the Athena engine."""

    enabled: bool = True
    settings: dict[str, Any] = field(default_factory=dict)

    def configure(self, **settings: Any) -> None:
        self.settings.update(settings)

    def run(self, **context: Any) -> dict[str, Any]:
        return {"component": "calendar", "enabled": self.enabled, "settings": self.settings, "context": context}
