from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Event:
    """
    Base class for all AQE internal events.

    Events describe something that has already happened.

    They are immutable so that once an event has been published,
    subscribers cannot accidentally modify the event received by
    other subscribers.
    """

    event_id: UUID
    occurred_at: datetime

    @classmethod
    def create(cls, **kwargs):
        """
        Convenience constructor that generates the event identity
        and timestamp automatically.
        """

        return cls(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            **kwargs,
        )
