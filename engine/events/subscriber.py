"""Event subscription helper."""

from engine.events.bus import EventBus, EventHandler


class Subscriber:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def on(self, event_type: str, handler: EventHandler) -> None:
        self.bus.subscribe(event_type, handler)
