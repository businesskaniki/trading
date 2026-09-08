from __future__ import annotations

import asyncio
import inspect
import logging
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from .exceptions import (
    RedisConsumerGroupError,
    RedisMessageError,
    RedisStreamError,
    RedisStreamNotFoundError,
)
from .streams import RedisStream, redis_stream

logger = logging.getLogger(__name__)


MessageHandler = Callable[
    [str, str, dict[str, Any]],
    Awaitable[None] | None,
]


class RedisStreamConsumer:
    """
    Production Redis Stream consumer for AQE.

    Responsibilities
    ----------------
    - Manage a Redis Stream consumer group.
    - Read messages using XREADGROUP.
    - Dispatch messages to an application handler.
    - ACK messages only after successful processing.
    - Recover stale pending messages.
    - Handle Redis Stream failures without killing the application.
    - Shut down cleanly.

    The consumer contains no trading/business logic.
    """

    def __init__(
        self,
        stream: RedisStream | None = None,
        *,
        stream_name: str = "aqe:events",
        group_name: str = "aqe",
        consumer_name: str | None = None,
        batch_size: int = 10,
        block_ms: int = 5000,
        claim_idle_ms: int = 60000,
        recovery_interval_ms: int = 30000,
    ) -> None:
        if not stream_name.strip():
            raise ValueError("stream_name cannot be empty.")

        if not group_name.strip():
            raise ValueError("group_name cannot be empty.")

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        if block_ms < 0:
            raise ValueError("block_ms cannot be negative.")

        if claim_idle_ms < 0:
            raise ValueError("claim_idle_ms cannot be negative.")

        if recovery_interval_ms <= 0:
            raise ValueError("recovery_interval_ms must be greater than zero.")

        self.stream = stream or redis_stream

        self.stream_name = stream_name.strip()
        self.group_name = group_name.strip()

        self.consumer_name = (
            consumer_name.strip()
            if consumer_name and consumer_name.strip()
            else self._default_consumer_name()
        )

        self.batch_size = batch_size
        self.block_ms = block_ms
        self.claim_idle_ms = claim_idle_ms
        self.recovery_interval_ms = recovery_interval_ms

        self._handler: MessageHandler | None = None

        self._running = False
        self._task: asyncio.Task[None] | None = None

        self._last_recovery_monotonic = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return whether the consumer is currently running."""
        return self._running

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Return the background consumer task."""
        return self._task

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        handler: MessageHandler,
    ) -> None:
        """
        Start the Redis Stream consumer.

        The consumer group is created before the background loop starts.
        """

        if not callable(handler):
            raise RedisMessageError("Consumer handler must be callable.")

        if self._running:
            logger.debug(
                "Redis Stream consumer already running. "
                "stream=%s group=%s consumer=%s",
                self.stream_name,
                self.group_name,
                self.consumer_name,
            )
            return

        self._handler = handler

        await self.ensure_group()

        self._running = True

        self._task = asyncio.create_task(
            self._consume_loop(),
            name=(f"redis-consumer:" f"{self.stream_name}:" f"{self.consumer_name}"),
        )

        logger.info(
            "Redis Stream consumer started. "
            "stream=%s group=%s consumer=%s "
            "batch_size=%s block_ms=%s claim_idle_ms=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
            self.batch_size,
            self.block_ms,
            self.claim_idle_ms,
        )

    async def stop(self) -> None:
        """
        Stop the consumer cleanly.
        """

        if not self._running and self._task is None:
            return

        logger.info(
            "Stopping Redis Stream consumer. " "stream=%s group=%s consumer=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
        )

        self._running = False

        task = self._task
        self._task = None

        if task is not None:
            if not task.done():
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Redis Stream consumer stopped with an error.")

        self._handler = None

        logger.info(
            "Redis Stream consumer stopped. " "stream=%s group=%s consumer=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
        )

    # ------------------------------------------------------------------
    # Consumer group
    # ------------------------------------------------------------------

    async def ensure_group(self) -> None:
        """
        Ensure that the Redis Stream consumer group exists.
        """

        try:
            await self.stream.create_consumer_group(
                self.stream_name,
                self.group_name,
                start_id="0",
                mkstream=True,
            )

        except RedisConsumerGroupError:
            raise

        except Exception as exc:
            raise RedisConsumerGroupError(
                "Failed to initialize Redis consumer group " f"'{self.group_name}'."
            ) from exc

    # ------------------------------------------------------------------
    # Normal consumption
    # ------------------------------------------------------------------

    async def consume_once(self) -> int:
        """
        Perform one Redis Stream consumption cycle.

        Returns:
            Number of successfully processed messages.

        A timeout resulting from an empty blocking read is not treated
        as a message-processing failure by this method. The underlying
        RedisStream abstraction is expected to translate transport
        errors into RedisStreamError.
        """

        if self._handler is None:
            raise RedisStreamError("Consumer handler has not been configured.")

        messages = await self.stream.read_group(
            self.stream_name,
            self.group_name,
            self.consumer_name,
            count=self.batch_size,
            block_ms=self.block_ms,
            start_id=">",
        )

        if not messages:
            return 0

        processed = 0

        for stream_name, entries in messages:
            for message_id, fields in entries:
                success = await self._process_message(
                    stream_name,
                    message_id,
                    fields,
                )

                if success:
                    processed += 1

        return processed

    # ------------------------------------------------------------------
    # Pending message recovery
    # ------------------------------------------------------------------

    async def recover_pending(
        self,
        *,
        count: int | None = None,
    ) -> int:
        """
        Recover stale pending messages.

        A pending message becomes eligible when its idle time is at
        least ``claim_idle_ms``.

        Returns:
            Number of successfully recovered messages.
        """

        if self._handler is None:
            raise RedisStreamError("Consumer handler has not been configured.")

        recovery_count = self.batch_size if count is None else count

        if recovery_count <= 0:
            raise RedisStreamError("Pending recovery count must be greater than zero.")

        try:
            entries = await self.stream.pending_entries(
                self.stream_name,
                self.group_name,
                count=recovery_count,
            )

        except RedisStreamNotFoundError:
            return 0

        if not entries:
            return 0

        stale_ids: list[str] = []

        for entry in entries:
            try:
                idle_time = int(
                    entry.get(
                        "time_since_delivered",
                        0,
                    )
                )
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring malformed Redis pending entry. "
                    "stream=%s group=%s entry=%r",
                    self.stream_name,
                    self.group_name,
                    entry,
                )
                continue

            if idle_time >= self.claim_idle_ms:
                stale_ids.append(str(entry["message_id"]))

        if not stale_ids:
            return 0

        recovered = await self.stream.claim(
            self.stream_name,
            self.group_name,
            self.consumer_name,
            stale_ids,
            min_idle_ms=self.claim_idle_ms,
        )

        processed = 0

        for message_id, fields in recovered:
            success = await self._process_message(
                self.stream_name,
                message_id,
                fields,
            )

            if success:
                processed += 1

        if processed:
            logger.info(
                "Recovered stale Redis Stream messages. "
                "stream=%s group=%s consumer=%s count=%s",
                self.stream_name,
                self.group_name,
                self.consumer_name,
                processed,
            )

        return processed

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """
        Main background consumption loop.

        Normal operation:

            recover pending messages periodically
            ↓
            read new messages
            ↓
            process
            ↓
            ACK

        Redis failures are retried without terminating the consumer.
        """

        recovery_interval_seconds = self.recovery_interval_ms / 1000.0

        while self._running:
            try:
                # ------------------------------------------------------
                # Periodic pending-message recovery
                # ------------------------------------------------------

                now = asyncio.get_running_loop().time()

                if now - self._last_recovery_monotonic >= recovery_interval_seconds:
                    try:
                        await self.recover_pending()

                    except RedisStreamNotFoundError:
                        await self.ensure_group()

                    except RedisStreamError:
                        logger.exception(
                            "Redis pending-message recovery failed. "
                            "stream=%s group=%s consumer=%s",
                            self.stream_name,
                            self.group_name,
                            self.consumer_name,
                        )

                    self._last_recovery_monotonic = now

                # ------------------------------------------------------
                # Consume new messages
                # ------------------------------------------------------

                processed = await self.consume_once()

                if processed:
                    logger.debug(
                        "Processed Redis Stream messages. "
                        "stream=%s group=%s consumer=%s count=%s",
                        self.stream_name,
                        self.group_name,
                        self.consumer_name,
                        processed,
                    )

            except asyncio.CancelledError:
                raise

            except RedisStreamNotFoundError:
                logger.warning(
                    "Redis Stream or consumer group unavailable. "
                    "Recreating group. stream=%s group=%s",
                    self.stream_name,
                    self.group_name,
                )

                try:
                    await self.ensure_group()

                except Exception:
                    logger.exception("Failed to recreate Redis consumer group.")

                    await self._sleep_before_retry()

            except RedisStreamError:
                logger.exception(
                    "Redis Stream consumer iteration failed. "
                    "stream=%s group=%s consumer=%s",
                    self.stream_name,
                    self.group_name,
                    self.consumer_name,
                )

                await self._sleep_before_retry()

            except Exception:
                logger.exception(
                    "Unexpected Redis Stream consumer error. "
                    "stream=%s group=%s consumer=%s",
                    self.stream_name,
                    self.group_name,
                    self.consumer_name,
                )

                await self._sleep_before_retry()

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        stream_name: str,
        message_id: str,
        fields: dict[str, Any],
    ) -> bool:
        """
        Process a single Redis Stream message.

        ACK is performed only after the handler completes successfully.

        If processing fails:

            handler failure
                ↓
            no ACK
                ↓
            message remains pending
                ↓
            future recovery can retry it
        """

        if self._handler is None:
            raise RedisStreamError("Consumer handler has not been configured.")

        try:
            result = self._handler(
                stream_name,
                message_id,
                fields,
            )

            if inspect.isawaitable(result):
                await result

            await self.stream.acknowledge(
                self.stream_name,
                self.group_name,
                message_id,
            )

            logger.debug(
                "Redis Stream message processed and acknowledged. "
                "stream=%s group=%s consumer=%s message_id=%s",
                stream_name,
                self.group_name,
                self.consumer_name,
                message_id,
            )

            return True

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Redis Stream message processing failed. "
                "Message remains pending. "
                "stream=%s group=%s consumer=%s message_id=%s",
                stream_name,
                self.group_name,
                self.consumer_name,
                message_id,
            )

            return False

    # ------------------------------------------------------------------
    # Retry handling
    # ------------------------------------------------------------------

    async def _sleep_before_retry(
        self,
        delay_seconds: float = 1.0,
    ) -> None:
        """
        Sleep before retrying a failed Redis operation.
        """

        if not self._running:
            return

        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    # Consumer identity
    # ------------------------------------------------------------------

    @staticmethod
    def _default_consumer_name() -> str:
        """
        Generate a process-specific consumer name.
        """

        hostname = socket.gethostname()

        try:
            task = asyncio.current_task()
            task_name = task.get_name() if task else "main"

        except RuntimeError:
            task_name = "main"

        return f"{hostname}:{task_name}"


# ---------------------------------------------------------------------------
# Default AQE consumer
# ---------------------------------------------------------------------------

redis_consumer = RedisStreamConsumer()
