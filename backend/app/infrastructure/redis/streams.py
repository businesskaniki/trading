from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from redis.exceptions import (
    ResponseError,
    TimeoutError as RedisTimeoutError,
)

from .client import RedisClient, redis_client
from .exceptions import (
    RedisConsumerGroupError,
    RedisMessageError,
    RedisOperationError,
    RedisStreamError,
    RedisStreamNotFoundError,
)

logger = logging.getLogger(__name__)


class RedisStream:
    """
    Production Redis Streams transport abstraction for AQE.

    Responsibilities:
        - consumer-group management
        - publishing messages
        - reading messages
        - acknowledging messages
        - inspecting pending messages
        - claiming stale messages
        - deleting messages
        - stream length
        - stream trimming

    This class contains Redis transport behavior only.
    It contains no trading or application business logic.
    """

    def __init__(
        self,
        client: RedisClient | None = None,
    ) -> None:
        self.client = client or redis_client

    # ------------------------------------------------------------------
    # Redis connection
    # ------------------------------------------------------------------

    @property
    def redis(self):
        """
        Return the active Redis connection.

        Raises:
            RedisOperationError:
                If Redis has not been connected.
        """
        try:
            return self.client.redis
        except Exception as exc:
            raise RedisOperationError("Redis client is not connected.") from exc

    # ------------------------------------------------------------------
    # Consumer groups
    # ------------------------------------------------------------------

    async def create_consumer_group(
        self,
        stream: str,
        group: str,
        *,
        start_id: str = "0",
        mkstream: bool = True,
    ) -> bool:
        """
        Create a Redis Stream consumer group.

        If the group already exists, this method returns True.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")

        if not start_id:
            raise RedisConsumerGroupError("Consumer group start_id cannot be empty.")

        try:
            await self.redis.xgroup_create(
                name=stream,
                groupname=group,
                id=start_id,
                mkstream=mkstream,
            )

            logger.info(
                "Redis consumer group created. " "stream=%s group=%s",
                stream,
                group,
            )

            return True

        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "Redis consumer group already exists. " "stream=%s group=%s",
                    stream,
                    group,
                )
                return True

            raise RedisConsumerGroupError(
                f"Failed to create consumer group '{group}' " f"for stream '{stream}'."
            ) from exc

        except Exception as exc:
            raise RedisConsumerGroupError(
                f"Failed to create consumer group '{group}' " f"for stream '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        stream: str,
        message: Mapping[str, Any],
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        """
        Publish a message to a Redis Stream.

        Returns:
            Redis-generated message ID.
        """

        self._validate_name(stream, "stream")

        if not isinstance(message, Mapping):
            raise RedisMessageError("Redis Stream message must be a mapping.")

        if not message:
            raise RedisMessageError("Redis Stream message cannot be empty.")

        if maxlen is not None and maxlen <= 0:
            raise RedisMessageError("Redis Stream maxlen must be greater than zero.")

        fields: dict[str, Any] = {}

        for key, value in message.items():
            if not isinstance(key, str) or not key:
                raise RedisMessageError(
                    "Redis Stream message field names must be " "non-empty strings."
                )

            if value is None:
                raise RedisMessageError(f"Redis Stream field '{key}' cannot be None.")

            fields[key] = value

        try:
            kwargs: dict[str, Any] = {}

            if maxlen is not None:
                kwargs["maxlen"] = maxlen
                kwargs["approximate"] = approximate

            message_id = await self.redis.xadd(
                name=stream,
                fields=fields,
                **kwargs,
            )

            logger.debug(
                "Redis Stream message published. " "stream=%s message_id=%s",
                stream,
                message_id,
            )

            return str(message_id)

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to publish message to Redis Stream " f"'{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Consumer-group reads
    # ------------------------------------------------------------------

    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int | None = 5000,
        start_id: str = ">",
    ) -> list[tuple[str, list[tuple[str, dict[str, Any]]]]]:
        """
        Read messages through a Redis consumer group.

        ``start_id=">"`` reads messages that have never previously
        been delivered to another consumer.

        A concrete message ID may be supplied for replay/recovery.

        A blocking read that reaches its timeout without receiving
        messages returns an empty list. This is normal Redis Stream
        behavior and is NOT treated as an error.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")
        self._validate_name(consumer, "consumer")

        if count <= 0:
            raise RedisStreamError("Redis Stream read count must be greater than zero.")

        if block_ms is not None and block_ms < 0:
            raise RedisStreamError("Redis Stream block_ms cannot be negative.")

        if not start_id:
            raise RedisStreamError("Redis Stream start_id cannot be empty.")

        try:
            kwargs: dict[str, Any] = {
                "groupname": group,
                "consumername": consumer,
                "streams": {
                    stream: start_id,
                },
                "count": count,
            }

            if block_ms is not None:
                kwargs["block"] = block_ms

            response = await self.redis.xreadgroup(**kwargs)

            # Redis returns an empty response when a blocking
            # XREADGROUP reaches its block timeout without data.
            if not response:
                return []

            return self._normalize_read_response(response)

        except RedisTimeoutError:
            # ----------------------------------------------------------
            # IMPORTANT
            #
            # A blocking Redis Stream read can reach the socket timeout.
            # When no message was received, this should not cause the
            # entire consumer to enter an error/retry cycle.
            # ----------------------------------------------------------

            logger.debug(
                "Redis Stream blocking read timed out with no message. "
                "stream=%s group=%s consumer=%s block_ms=%s",
                stream,
                group,
                consumer,
                block_ms,
            )

            return []

        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                raise RedisStreamNotFoundError(
                    f"Redis Stream '{stream}' or consumer group "
                    f"'{group}' does not exist."
                ) from exc

            raise RedisStreamError(f"Failed to read Redis Stream '{stream}'.") from exc

        except Exception as exc:
            raise RedisStreamError(f"Failed to read Redis Stream '{stream}'.") from exc

    # ------------------------------------------------------------------
    # Acknowledgement
    # ------------------------------------------------------------------

    async def acknowledge(
        self,
        stream: str,
        group: str,
        *message_ids: str,
    ) -> int:
        """
        Acknowledge one or more messages.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")

        if not message_ids:
            raise RedisMessageError(
                "At least one message ID is required " "for acknowledgement."
            )

        for message_id in message_ids:
            if not isinstance(message_id, str) or not message_id:
                raise RedisMessageError(
                    "Redis Stream message IDs must be " "non-empty strings."
                )

        try:
            acknowledged = await self.redis.xack(
                stream,
                group,
                *message_ids,
            )

            logger.debug(
                "Redis Stream messages acknowledged. " "stream=%s group=%s count=%s",
                stream,
                group,
                acknowledged,
            )

            return int(acknowledged)

        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                raise RedisStreamNotFoundError(
                    f"Redis Stream '{stream}' or consumer group "
                    f"'{group}' does not exist."
                ) from exc

            raise RedisStreamError(
                f"Failed to acknowledge messages in stream " f"'{stream}'."
            ) from exc

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to acknowledge messages in stream " f"'{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Pending summary
    # ------------------------------------------------------------------

    async def pending(
        self,
        stream: str,
        group: str,
    ) -> dict[str, Any]:
        """
        Return summary information about pending messages.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")

        try:
            response = await self.redis.xpending(
                stream,
                group,
            )

            return dict(response)

        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                raise RedisStreamNotFoundError(
                    f"Redis Stream '{stream}' or consumer group "
                    f"'{group}' does not exist."
                ) from exc

            raise RedisStreamError(
                f"Failed to inspect pending messages " f"for '{stream}'."
            ) from exc

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to inspect pending messages " f"for '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Pending entries
    # ------------------------------------------------------------------

    async def pending_entries(
        self,
        stream: str,
        group: str,
        *,
        count: int = 100,
        start: str = "-",
        end: str = "+",
    ) -> list[dict[str, Any]]:
        """
        Return detailed pending-message information.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")

        if count <= 0:
            raise RedisStreamError("Pending entry count must be greater than zero.")

        try:
            response = await self.redis.xpending_range(
                name=stream,
                groupname=group,
                min=start,
                max=end,
                count=count,
            )

            entries: list[dict[str, Any]] = []

            for entry in response:
                if isinstance(entry, dict):
                    entries.append(dict(entry))
                    continue

                if isinstance(entry, (list, tuple)) and len(entry) >= 4:
                    entries.append(
                        {
                            "message_id": str(entry[0]),
                            "consumer": str(entry[1]),
                            "time_since_delivered": int(entry[2]),
                            "times_delivered": int(entry[3]),
                        }
                    )

            return entries

        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                raise RedisStreamNotFoundError(
                    f"Redis Stream '{stream}' or consumer group "
                    f"'{group}' does not exist."
                ) from exc

            raise RedisStreamError(
                f"Failed to retrieve pending entries " f"for stream '{stream}'."
            ) from exc

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to retrieve pending entries " f"for stream '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Claim stale messages
    # ------------------------------------------------------------------

    async def claim(
        self,
        stream: str,
        group: str,
        consumer: str,
        message_ids: list[str],
        *,
        min_idle_ms: int = 60000,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Claim stale pending messages for this consumer.
        """

        self._validate_name(stream, "stream")
        self._validate_name(group, "consumer group")
        self._validate_name(consumer, "consumer")

        if min_idle_ms < 0:
            raise RedisStreamError("min_idle_ms cannot be negative.")

        if not message_ids:
            return []

        for message_id in message_ids:
            if not isinstance(message_id, str) or not message_id:
                raise RedisMessageError(
                    "Redis Stream message IDs must be " "non-empty strings."
                )

        try:
            response = await self.redis.xclaim(
                name=stream,
                groupname=group,
                consumername=consumer,
                min_idle_time=min_idle_ms,
                message_ids=message_ids,
            )

            return [
                (
                    str(message_id),
                    dict(fields),
                )
                for message_id, fields in response
            ]

        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                raise RedisStreamNotFoundError(
                    f"Redis Stream '{stream}' or consumer group "
                    f"'{group}' does not exist."
                ) from exc

            raise RedisStreamError(
                f"Failed to claim messages from " f"stream '{stream}'."
            ) from exc

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to claim messages from " f"stream '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(
        self,
        stream: str,
        *message_ids: str,
    ) -> int:
        """
        Delete specific messages from a Redis Stream.
        """

        self._validate_name(stream, "stream")

        if not message_ids:
            raise RedisMessageError(
                "At least one message ID is required " "for deletion."
            )

        for message_id in message_ids:
            if not isinstance(message_id, str) or not message_id:
                raise RedisMessageError(
                    "Redis Stream message IDs must be " "non-empty strings."
                )

        try:
            deleted = await self.redis.xdel(
                stream,
                *message_ids,
            )

            return int(deleted)

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to delete messages from " f"stream '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Length
    # ------------------------------------------------------------------

    async def length(
        self,
        stream: str,
    ) -> int:
        """
        Return the current Redis Stream length.
        """

        self._validate_name(stream, "stream")

        try:
            return int(await self.redis.xlen(stream))

        except Exception as exc:
            raise RedisStreamError(
                f"Failed to retrieve length of " f"stream '{stream}'."
            ) from exc

    # ------------------------------------------------------------------
    # Trim
    # ------------------------------------------------------------------

    async def trim(
        self,
        stream: str,
        *,
        maxlen: int,
        approximate: bool = True,
    ) -> int:
        """
        Trim a Redis Stream to a maximum length.
        """

        self._validate_name(stream, "stream")

        if maxlen <= 0:
            raise RedisStreamError("Stream maxlen must be greater than zero.")

        try:
            removed = await self.redis.xtrim(
                stream,
                maxlen=maxlen,
                approximate=approximate,
            )

            return int(removed)

        except Exception as exc:
            raise RedisStreamError(f"Failed to trim stream '{stream}'.") from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_name(
        value: str,
        field_name: str,
    ) -> None:
        """
        Validate Redis Stream/group/consumer names.
        """

        if not isinstance(value, str):
            raise RedisStreamError(f"{field_name.capitalize()} name must be a string.")

        if not value.strip():
            raise RedisStreamError(f"{field_name.capitalize()} name cannot be empty.")

    # ------------------------------------------------------------------
    # Response normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_read_response(
        response: Any,
    ) -> list[tuple[str, list[tuple[str, dict[str, Any]]]]]:
        """
        Normalize redis-py's XREADGROUP response.
        """

        if not response:
            return []

        normalized: list[tuple[str, list[tuple[str, dict[str, Any]]]]] = []

        try:
            for stream_name, messages in response:
                normalized_messages: list[tuple[str, dict[str, Any]]] = []

                for message_id, fields in messages:
                    if not isinstance(fields, Mapping):
                        raise RedisMessageError(
                            "Redis Stream message fields " "must be a mapping."
                        )

                    normalized_messages.append(
                        (
                            str(message_id),
                            dict(fields),
                        )
                    )

                normalized.append(
                    (
                        str(stream_name),
                        normalized_messages,
                    )
                )

        except RedisMessageError:
            raise

        except Exception as exc:
            raise RedisMessageError(
                "Failed to normalize Redis Stream response."
            ) from exc

        return normalized


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

redis_stream = RedisStream()
