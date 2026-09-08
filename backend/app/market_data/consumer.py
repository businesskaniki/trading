from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.events.bus import event_bus
from app.events.market import MarketTickEvent
from app.infrastructure.redis.consumer import RedisStreamConsumer
from app.infrastructure.redis.exceptions import RedisMessageError
from app.market_data.models import MarketTick

logger = logging.getLogger(__name__)


class MarketDataConsumer:
    """
    Consumes market-data events from the Redis Stream and publishes
    normalized MarketTickEvent instances to the AQE EventBus.
    """

    STREAM_NAME = "aqe:market-data"
    GROUP_NAME = "aqe-market-data"
    CONSUMER_NAME = "aqe-market-data-consumer"
    EXPECTED_EVENT_TYPE = "MarketTickEvent"

    def __init__(
        self,
        *,
        stream_name: str = STREAM_NAME,
        group_name: str = GROUP_NAME,
        consumer_name: str = CONSUMER_NAME,
    ) -> None:
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name

        self._consumer = RedisStreamConsumer(
            stream_name=self.stream_name,
            group_name=self.group_name,
            consumer_name=self.consumer_name,
        )

        self._started = False

    async def start(self) -> None:
        """
        Start consuming market-data messages from Redis.
        """
        if self._started:
            logger.warning(
                "Market-data consumer already started. "
                "stream=%s group=%s consumer=%s",
                self.stream_name,
                self.group_name,
                self.consumer_name,
            )
            return

        await self._consumer.start(self._handle_message)

        self._started = True

        logger.info(
            "Market-data consumer started. " "stream=%s group=%s consumer=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
        )

    async def stop(self) -> None:
        """
        Stop consuming market-data messages.
        """
        if not self._started:
            return

        await self._consumer.stop()

        self._started = False

        logger.info(
            "Market-data consumer stopped. " "stream=%s group=%s consumer=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
        )

    async def _handle_message(
        self,
        stream_name: str,
        message_id: str,
        fields: dict[str, Any],
    ) -> None:
        """
        Process one Redis Stream message.

        RedisStreamConsumer invokes handlers with:

            stream_name
            message_id
            fields

        The expected message envelope is:

            event_id
            event_type
            occurred_at
            payload

        The payload contains the serialized MarketTick.
        """

        try:
            # ---------------------------------------------------------
            # Validate event type
            # ---------------------------------------------------------

            event_type = fields.get("event_type")

            if event_type != self.EXPECTED_EVENT_TYPE:
                raise RedisMessageError(
                    f"Unexpected market-data event type: {event_type!r}. "
                    f"Expected {self.EXPECTED_EVENT_TYPE!r}."
                )

            # ---------------------------------------------------------
            # Extract event envelope
            # ---------------------------------------------------------

            event_id = fields.get("event_id")
            occurred_at_raw = fields.get("occurred_at")
            payload_raw = fields.get("payload")

            if not event_id:
                raise RedisMessageError(
                    "Market-data Redis message is missing event_id."
                )

            if not occurred_at_raw:
                raise RedisMessageError(
                    "Market-data Redis message is missing occurred_at."
                )

            if payload_raw is None:
                raise RedisMessageError("Market-data Redis message is missing payload.")

            # ---------------------------------------------------------
            # Parse occurred_at
            # ---------------------------------------------------------

            try:
                occurred_at = datetime.fromisoformat(str(occurred_at_raw))
            except (TypeError, ValueError) as exc:
                raise RedisMessageError(
                    "Market-data Redis message contains an invalid "
                    f"occurred_at value: {occurred_at_raw!r}"
                ) from exc

            # ---------------------------------------------------------
            # Parse JSON payload
            # ---------------------------------------------------------

            try:
                if isinstance(payload_raw, bytes):
                    payload_raw = payload_raw.decode("utf-8")

                payload = json.loads(payload_raw)

            except (UnicodeDecodeError, TypeError, ValueError) as exc:
                raise RedisMessageError(
                    "Market-data Redis message contains invalid JSON payload."
                ) from exc

            if not isinstance(payload, dict):
                raise RedisMessageError(
                    "Market-data Redis payload must be a JSON object."
                )

            # ---------------------------------------------------------
            # Extract MarketTick fields
            # ---------------------------------------------------------

            try:
                symbol = payload.get("symbol")
                timestamp = payload.get("timestamp")
                bid = payload.get("bid")
                ask = payload.get("ask")
                last = payload.get("last", 0.0)
                volume = payload.get("volume", 0)
                volume_real = payload.get("volume_real", 0.0)

                if symbol is None:
                    raise ValueError("Missing symbol.")

                if timestamp is None:
                    raise ValueError("Missing timestamp.")

                if bid is None:
                    raise ValueError("Missing bid.")

                if ask is None:
                    raise ValueError("Missing ask.")

                tick = MarketTick(
                    symbol=str(symbol),
                    timestamp=int(timestamp),
                    bid=float(bid),
                    ask=float(ask),
                    last=float(last),
                    volume=int(volume),
                    volume_real=float(volume_real),
                )

            except (TypeError, ValueError, OverflowError) as exc:
                raise RedisMessageError(
                    "Market-data Redis payload could not be converted "
                    "into MarketTick."
                ) from exc

            # ---------------------------------------------------------
            # Validate normalized tick
            # ---------------------------------------------------------

            if not tick.is_valid():
                raise RedisMessageError(
                    f"Invalid MarketTick received for symbol={tick.symbol!r}."
                )

            # ---------------------------------------------------------
            # Reconstruct MarketTickEvent
            # ---------------------------------------------------------

            event = MarketTickEvent(
                event_id=event_id,
                occurred_at=occurred_at,
                tick=tick,
            )

            # ---------------------------------------------------------
            # Publish to AQE EventBus
            # ---------------------------------------------------------

            await event_bus.publish(event)

            logger.debug(
                "MarketTickEvent published to EventBus. "
                "stream=%s message_id=%s event_id=%s "
                "symbol=%s bid=%s ask=%s",
                stream_name,
                message_id,
                event.event_id,
                tick.symbol,
                tick.bid,
                tick.ask,
            )

        except RedisMessageError:
            raise

        except Exception as exc:
            logger.exception(
                "Failed to process market-data Redis message. "
                "stream=%s message_id=%s",
                stream_name,
                message_id,
            )

            raise RedisMessageError(
                "Market-data Redis message could not be processed."
            ) from exc


market_data_redis_consumer = MarketDataConsumer()
