from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from math import isfinite
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

    Invalid broker payloads are rejected with detailed diagnostics
    so the underlying Redis message remains pending and can be
    inspected/reprocessed rather than silently discarded.
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

        Expected message envelope:

            event_id
            event_type
            occurred_at
            payload

        The payload contains the serialized MarketTick.

        Invalid messages raise RedisMessageError so the underlying
        Redis infrastructure can handle them appropriately.
        """

        # =============================================================
        # DEBUG: RAW MESSAGE RECEIVED FROM REDIS
        # =============================================================

        logger.info(
            "📥 AQE RECEIVED MARKET-DATA MESSAGE FROM REDIS | "
            "stream=%s | message_id=%s | fields=%r",
            stream_name,
            message_id,
            fields,
        )

        try:
            # =========================================================
            # Validate event type
            # =========================================================

            event_type = fields.get("event_type")

            logger.info(
                "📨 AQE MARKET-DATA EVENT TYPE | " "message_id=%s | event_type=%r",
                message_id,
                event_type,
            )

            if event_type != self.EXPECTED_EVENT_TYPE:
                raise RedisMessageError(
                    "Unexpected market-data event type: "
                    f"{event_type!r}. "
                    f"Expected {self.EXPECTED_EVENT_TYPE!r}."
                )

            # =========================================================
            # Extract event envelope
            # =========================================================

            event_id = fields.get("event_id")
            occurred_at_raw = fields.get("occurred_at")
            payload_raw = fields.get("payload")

            logger.info(
                "📦 AQE MARKET-DATA ENVELOPE | "
                "message_id=%s | event_id=%r | occurred_at=%r",
                message_id,
                event_id,
                occurred_at_raw,
            )

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

            # =========================================================
            # Parse occurred_at
            # =========================================================

            try:
                occurred_at = datetime.fromisoformat(
                    str(occurred_at_raw).replace(
                        "Z",
                        "+00:00",
                    )
                )

                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                else:
                    occurred_at = occurred_at.astimezone(timezone.utc)

            except (TypeError, ValueError) as exc:
                raise RedisMessageError(
                    "Market-data Redis message contains an invalid "
                    f"occurred_at value: {occurred_at_raw!r}"
                ) from exc

            # =========================================================
            # Parse JSON payload
            # =========================================================

            try:
                if isinstance(payload_raw, bytes):
                    payload_raw = payload_raw.decode("utf-8")

                elif not isinstance(payload_raw, str):
                    payload_raw = str(payload_raw)

                payload = json.loads(payload_raw)

            except (
                UnicodeDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                logger.error(
                    "❌ INVALID MARKET-DATA JSON | "
                    "stream=%s | message_id=%s | event_id=%s | "
                    "payload=%r",
                    stream_name,
                    message_id,
                    event_id,
                    payload_raw,
                )

                raise RedisMessageError(
                    "Market-data Redis message contains invalid " "JSON payload."
                ) from exc

            if not isinstance(payload, dict):
                raise RedisMessageError(
                    "Market-data Redis payload must be a JSON object."
                )

            # =========================================================
            # DEBUG: ACTUAL PAYLOAD AQE RECEIVED
            # =========================================================

            logger.info(
                "📊 AQE RECEIVED MARKET-DATA PAYLOAD | "
                "message_id=%s | event_id=%s | payload=%r",
                message_id,
                event_id,
                payload,
            )

            # =========================================================
            # Extract MarketTick fields
            # =========================================================

            symbol = payload.get("symbol")
            timestamp = payload.get("timestamp")
            bid = payload.get("bid")
            ask = payload.get("ask")

            last = payload.get("last", 0.0)
            volume = payload.get("volume", 0)
            volume_real = payload.get(
                "volume_real",
                0.0,
            )

            # =========================================================
            # DEBUG: EXTRACTED MARKET VALUES
            # =========================================================

            logger.info(
                "🔎 AQE EXTRACTED TICK VALUES | "
                "message_id=%s | "
                "symbol=%r | "
                "timestamp=%r | "
                "bid=%r | "
                "ask=%r | "
                "last=%r | "
                "volume=%r | "
                "volume_real=%r",
                message_id,
                symbol,
                timestamp,
                bid,
                ask,
                last,
                volume,
                volume_real,
            )

            # =========================================================
            # Required fields
            # =========================================================

            missing_fields: list[str] = []

            if symbol is None:
                missing_fields.append("symbol")

            if timestamp is None:
                missing_fields.append("timestamp")

            if bid is None:
                missing_fields.append("bid")

            if ask is None:
                missing_fields.append("ask")

            if missing_fields:
                logger.error(
                    "❌ MARKET-DATA PAYLOAD MISSING REQUIRED FIELDS | "
                    "stream=%s | message_id=%s | event_id=%s | "
                    "symbol=%r | missing=%s | payload=%r",
                    stream_name,
                    message_id,
                    event_id,
                    symbol,
                    missing_fields,
                    payload,
                )

                raise RedisMessageError(
                    "Market-data Redis payload is missing required "
                    f"fields: {', '.join(missing_fields)}."
                )

            # =========================================================
            # Convert MarketTick
            # =========================================================

            try:
                normalized_symbol = str(symbol).strip()

                if not normalized_symbol:
                    raise ValueError("symbol must not be empty")

                normalized_timestamp = self._parse_timestamp(timestamp)

                normalized_bid = self._parse_float(
                    bid,
                    "bid",
                )

                normalized_ask = self._parse_float(
                    ask,
                    "ask",
                )

                normalized_last = self._parse_float(
                    last,
                    "last",
                )

                normalized_volume = self._parse_int(
                    volume,
                    "volume",
                )

                normalized_volume_real = self._parse_float(
                    volume_real,
                    "volume_real",
                )

                tick = MarketTick(
                    symbol=normalized_symbol,
                    timestamp=normalized_timestamp,
                    bid=normalized_bid,
                    ask=normalized_ask,
                    last=normalized_last,
                    volume=normalized_volume,
                    volume_real=normalized_volume_real,
                )

            except (
                TypeError,
                ValueError,
                OverflowError,
            ) as exc:
                logger.error(
                    "❌ MARKET-DATA COULD NOT BE CONVERTED "
                    "TO MarketTick | "
                    "stream=%s | message_id=%s | event_id=%s | "
                    "symbol=%r | error=%s | payload=%r",
                    stream_name,
                    message_id,
                    event_id,
                    symbol,
                    exc,
                    payload,
                )

                raise RedisMessageError(
                    "Market-data Redis payload could not be "
                    "converted into MarketTick: "
                    f"{exc}"
                ) from exc

            # =========================================================
            # Validate normalized tick
            # =========================================================

            validation_errors = tick.validation_errors()

            if validation_errors:
                logger.error(
                    "❌ INVALID MarketTick RECEIVED | "
                    "stream=%s | message_id=%s | event_id=%s | "
                    "symbol=%s | timestamp=%s | datetime=%s | "
                    "bid=%s | ask=%s | last=%s | volume=%s | "
                    "volume_real=%s | spread=%s | "
                    "validation_errors=%s | raw_payload=%r",
                    stream_name,
                    message_id,
                    event_id,
                    tick.symbol,
                    tick.timestamp,
                    tick.datetime.isoformat(),
                    tick.bid,
                    tick.ask,
                    tick.last,
                    tick.volume,
                    tick.volume_real,
                    tick.spread,
                    validation_errors,
                    payload,
                )

                raise RedisMessageError(
                    "Invalid MarketTick received for "
                    f"symbol={tick.symbol!r}: " + "; ".join(validation_errors)
                )

            # =========================================================
            # DEBUG: VALID MARKET TICK
            # =========================================================

            logger.info(
                "✅ AQE MARKET TICK VALIDATED | "
                "message_id=%s | event_id=%s | "
                "symbol=%s | timestamp=%s | "
                "bid=%s | ask=%s | last=%s | "
                "volume=%s | volume_real=%s | spread=%s",
                message_id,
                event_id,
                tick.symbol,
                tick.timestamp,
                tick.bid,
                tick.ask,
                tick.last,
                tick.volume,
                tick.volume_real,
                tick.spread,
            )

            # =========================================================
            # Reconstruct MarketTickEvent
            # =========================================================

            event = MarketTickEvent(
                event_id=event_id,
                occurred_at=occurred_at,
                tick=tick,
            )

            # =========================================================
            # Publish to AQE EventBus
            # =========================================================

            await event_bus.publish(event)

            # =========================================================
            # DEBUG: SUCCESSFULLY ENTERED AQE EVENT BUS
            # =========================================================

            logger.info(
                "🚀 AQE MARKET-DATA EVENT PUBLISHED "
                "TO EVENT BUS | "
                "message_id=%s | event_id=%s | "
                "symbol=%s | timestamp=%s | "
                "bid=%s | ask=%s",
                message_id,
                event.event_id,
                tick.symbol,
                tick.timestamp,
                tick.bid,
                tick.ask,
            )

            logger.debug(
                "MarketTickEvent published to EventBus. "
                "stream=%s message_id=%s event_id=%s "
                "symbol=%s timestamp=%s bid=%s ask=%s "
                "last=%s volume=%s volume_real=%s",
                stream_name,
                message_id,
                event.event_id,
                tick.symbol,
                tick.timestamp,
                tick.bid,
                tick.ask,
                tick.last,
                tick.volume,
                tick.volume_real,
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

    # ==================================================================
    # VALUE PARSING
    # ==================================================================

    @staticmethod
    def _parse_timestamp(value: Any) -> int:
        """
        Convert a Redis payload timestamp into a Unix timestamp.

        Accepted values:

            int
            float
            numeric string

        The result must be a positive integer.
        """

        if isinstance(value, bool):
            raise ValueError("timestamp must not be boolean")

        if isinstance(value, int):
            result = value

        elif isinstance(value, float):
            if not isfinite(value):
                raise ValueError(f"timestamp must be finite, got {value!r}")

            result = int(value)

        elif isinstance(value, str):
            raw = value.strip()

            if not raw:
                raise ValueError("timestamp must not be empty")

            try:
                numeric = float(raw)

            except ValueError as exc:
                raise ValueError(f"timestamp is not numeric: {value!r}") from exc

            if not isfinite(numeric):
                raise ValueError(f"timestamp must be finite, got {value!r}")

            result = int(numeric)

        else:
            raise TypeError(
                "timestamp must be an integer-compatible value, "
                f"got {type(value).__name__}"
            )

        if result <= 0:
            raise ValueError(f"timestamp must be greater than 0, got {result}")

        return result

    @staticmethod
    def _parse_float(
        value: Any,
        field_name: str,
    ) -> float:
        """
        Convert a payload value to a finite float.
        """

        if isinstance(value, bool):
            raise ValueError(f"{field_name} must not be boolean")

        try:
            result = float(value)

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(f"{field_name} is not a valid number: {value!r}") from exc

        if not isfinite(result):
            raise ValueError(f"{field_name} must be finite, got {value!r}")

        return result

    @staticmethod
    def _parse_int(
        value: Any,
        field_name: str,
    ) -> int:
        """
        Convert a payload value to an integer.

        Numeric strings and integer-valued floats are accepted.
        """

        if isinstance(value, bool):
            raise ValueError(f"{field_name} must not be boolean")

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if not isfinite(value):
                raise ValueError(f"{field_name} must be finite, got {value!r}")

            if not value.is_integer():
                raise ValueError(f"{field_name} must be an integer, got {value!r}")

            return int(value)

        if isinstance(value, str):
            raw = value.strip()

            if not raw:
                raise ValueError(f"{field_name} must not be empty")

            try:
                numeric = float(raw)

            except ValueError as exc:
                raise ValueError(
                    f"{field_name} is not a valid integer: {value!r}"
                ) from exc

            if not isfinite(numeric):
                raise ValueError(f"{field_name} must be finite, got {value!r}")

            if not numeric.is_integer():
                raise ValueError(f"{field_name} must be an integer, got {value!r}")

            return int(numeric)

        raise TypeError(
            f"{field_name} must be integer-compatible, " f"got {type(value).__name__}"
        )


market_data_redis_consumer = MarketDataConsumer()
