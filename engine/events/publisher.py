"""Event publishing helper."""

from engine.events.bus import Event, EventBus


class Publisher:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def publish(self, event_type: str, **payload: object) -> int:
        return self.bus.publish(Event(type=event_type, payload=dict(payload)))
