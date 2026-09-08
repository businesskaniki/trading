from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .client import RedisClient, redis_client

logger = logging.getLogger(__name__)


class RedisPublisherError(Exception):
    """
    Raised when publishing to Redis fails.
    """


class RedisPublisher:
    """
    Publishes MT5 Bridge events to Redis Streams.

    This class is intentionally transport-focused.

    It does not know anything about:
        - strategies
        - risk
        - execution
        - portfolios
        - trading decisions

    Its responsibility is only to create a consistent event envelope
    and publish it to Redis.
    """

    def __init__(
        self,
        client: RedisClient | None = None,
        *,
        default_stream: str = "aqe:market-data",
        maxlen: int | None = 100_000,
        approximate_trim: bool = True,
    ) -> None:
        if not default_stream.strip():
            raise ValueError("default_stream cannot be empty.")

        if maxlen is not None and maxlen <= 0:
            raise ValueError("maxlen must be greater than zero.")

        self.client = client or redis_client

        self.default_stream = default_stream.strip()
        self.maxlen = maxlen
        self.approximate_trim = approximate_trim

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        stream: str | None = None,
    ) -> str:
        """
        Publish an event to a Redis Stream.

        Args:
            event_type:
                Logical event type.

            payload:
                Event payload.

            stream:
                Optional target stream.

        Returns:
            Redis Stream message ID.
        """
        if not isinstance(event_type, str):
            raise RedisPublisherError("event_type must be a string.")

        event_type = event_type.strip()

        if not event_type:
            raise RedisPublisherError("event_type cannot be empty.")

        if not isinstance(payload, dict):
            raise RedisPublisherError("payload must be a dictionary.")

        target_stream = (
            stream.strip()
            if isinstance(stream, str) and stream.strip()
            else self.default_stream
        )

        event_id = str(uuid4())

        occurred_at = datetime.now(timezone.utc).isoformat()

        try:
            serialized_payload = json.dumps(
                payload,
                separators=(",", ":"),
                ensure_ascii=False,
            )

        except (TypeError, ValueError) as exc:
            raise RedisPublisherError(
                f"Unable to serialize payload " f"for event '{event_type}'."
            ) from exc

        message = {
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "payload": serialized_payload,
        }

        try:
            kwargs: dict[str, Any] = {}

            if self.maxlen is not None:
                kwargs["maxlen"] = self.maxlen
                kwargs["approximate"] = self.approximate_trim

            message_id = await self.client.redis.xadd(
                name=target_stream,
                fields=message,
                **kwargs,
            )

        except Exception as exc:
            logger.exception(
                "Failed to publish Redis event. " "event_type=%s stream=%s",
                event_type,
                target_stream,
            )

            raise RedisPublisherError(
                f"Failed to publish event "
                f"'{event_type}' "
                f"to Redis Stream "
                f"'{target_stream}'."
            ) from exc

        logger.debug(
            "Redis event published. "
            "event_id=%s event_type=%s "
            "stream=%s message_id=%s",
            event_id,
            event_type,
            target_stream,
            message_id,
        )

        return str(message_id)


redis_publisher = RedisPublisher()
