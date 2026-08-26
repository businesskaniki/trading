"""Common event handlers."""

from engine.events.bus import Event


class MemoryEventHandler:
    """Stores received events for tests, debugging, and dry-runs."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)
