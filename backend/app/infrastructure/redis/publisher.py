from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from app.events import Event

from .exceptions import RedisSerializationError, RedisStreamError
from .streams import RedisStream, redis_stream

logger = logging.getLogger(__name__)


class RedisStreamPublisher:
    """
    Publishes AQE events to Redis Streams.

    Responsibilities:
        - serialize AQE events
        - attach standard event metadata
        - publish messages through RedisStream
        - keep Redis transport concerns isolated from domain events

    This publisher does not contain business logic and does not know
    anything about strategies, risk, execution, MT5, or the frontend.
    """

    def __init__(
        self,
        stream: RedisStream | None = None,
        *,
        default_stream: str = "aqe:events",
        maxlen: int | None = 100_000,
        approximate_trim: bool = True,
    ) -> None:
        if not default_stream or not default_stream.strip():
            raise ValueError("default_stream cannot be empty.")

        if maxlen is not None and maxlen <= 0:
            raise ValueError("maxlen must be greater than zero.")

        self.stream = stream or redis_stream
        self.default_stream = default_stream.strip()
        self.maxlen = maxlen
        self.approximate_trim = approximate_trim

    async def publish(
        self,
        event: Event,
        *,
        stream: str | None = None,
    ) -> str:
        """
        Publish an AQE event to a Redis Stream.

        Args:
            event:
                AQE Event instance to publish.

            stream:
                Optional target stream. When omitted, the default stream
                is used.

        Returns:
            Redis Stream message ID.
        """
        if not isinstance(event, Event):
            raise RedisStreamError("Only AQE Event instances can be published.")

        target_stream = (
            stream.strip()
            if isinstance(stream, str) and stream.strip()
            else self.default_stream
        )

        try:
            payload = self._serialize_event(event)

            message = {
                "event_id": str(event.event_id),
                "event_type": type(event).__name__,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": json.dumps(
                    payload,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            }

        except RedisSerializationError:
            raise

        except Exception as exc:
            raise RedisSerializationError(
                f"Failed to serialize event " f"'{type(event).__name__}'."
            ) from exc

        try:
            message_id = await self.stream.publish(
                target_stream,
                message,
                maxlen=self.maxlen,
                approximate=self.approximate_trim,
            )

        except Exception as exc:
            if isinstance(exc, RedisStreamError):
                raise

            raise RedisStreamError(
                f"Failed to publish event "
                f"'{type(event).__name__}' "
                f"to stream '{target_stream}'."
            ) from exc

        logger.debug(
            "AQE event published. " "event_type=%s event_id=%s stream=%s message_id=%s",
            type(event).__name__,
            event.event_id,
            target_stream,
            message_id,
        )

        return message_id

    async def publish_many(
        self,
        events: list[Event],
        *,
        stream: str | None = None,
    ) -> list[str]:
        """
        Publish multiple AQE events sequentially.

        Returns:
            Redis message IDs in the same order as the supplied events.

        Notes:
            This method intentionally preserves event order. A future
            pipeline/batching implementation can be introduced without
            changing the public publisher interface.
        """
        if not isinstance(events, list):
            raise RedisStreamError("events must be provided as a list.")

        message_ids: list[str] = []

        for event in events:
            message_id = await self.publish(
                event,
                stream=stream,
            )
            message_ids.append(message_id)

        return message_ids

    @classmethod
    def _serialize_event(
        cls,
        event: Event,
    ) -> dict[str, Any]:
        """
        Convert an AQE Event into a JSON-compatible dictionary.

        Dataclasses are converted recursively. UUIDs, datetimes, enums,
        dates, mappings, lists, tuples, and sets are handled explicitly.
        """
        try:
            if not is_dataclass(event):
                raise RedisSerializationError(
                    f"Event '{type(event).__name__}' must be a dataclass."
                )

            data = asdict(event)

            return cls._to_json_compatible(data)

        except RedisSerializationError:
            raise

        except Exception as exc:
            raise RedisSerializationError(
                f"Unable to serialize event " f"'{type(event).__name__}'."
            ) from exc

    @classmethod
    def _to_json_compatible(
        cls,
        value: Any,
    ) -> Any:
        """
        Recursively convert supported Python values into JSON-compatible
        structures.
        """
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, Enum):
            return cls._to_json_compatible(value.value)

        if is_dataclass(value):
            return cls._to_json_compatible(asdict(value))

        if isinstance(value, dict):
            return {
                str(key): cls._to_json_compatible(item) for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._to_json_compatible(item) for item in value]

        try:
            json.dumps(value)
            return value

        except (TypeError, ValueError) as exc:
            raise RedisSerializationError(
                f"Unsupported value type during event serialization: "
                f"{type(value).__name__}."
            ) from exc


redis_publisher = RedisStreamPublisher()
