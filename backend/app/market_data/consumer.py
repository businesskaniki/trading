from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.database.models.account_symbol import AccountSymbol
from app.database.models.symbol import Symbol
from app.database.session import SessionLocal
from app.events.bus import event_bus
from app.events.market import MarketTickEvent
from app.infrastructure.redis.consumer import RedisStreamConsumer
from app.infrastructure.redis.exceptions import RedisMessageError
from app.market_data.models import MarketTick

logger = logging.getLogger(__name__)


class MarketDataConsumer:
    """
    Consume market-data events from Redis and publish normalized
    MarketTickEvent instances to the AQE EventBus.

    When account_id is supplied, broker-facing symbols are resolved
    against that account's enabled AccountSymbol mappings.

    Example:

        Incoming broker symbol: XAUUSD.s
        Canonical AQE symbol:   XAUUSD

    The MarketTick published to the EventBus uses the canonical AQE
    symbol so StrategyDispatcher can route it to matching strategies.

    Broker-facing symbol identities remain authoritative in
    AccountSymbol persistence and continue to be resolved by the
    execution infrastructure.

    Symbol mappings are loaded when the consumer starts. They are not
    queried from PostgreSQL for every incoming tick.

    When account_id is omitted, symbol mapping is disabled to preserve
    compatibility with standalone consumers and existing tests.

    Invalid broker payloads raise RedisMessageError so the Redis
    consumer can apply its configured message failure handling.

    Stream-health statistics are exposed through status().
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
        account_id: UUID | None = None,
        session_factory=SessionLocal,
    ) -> None:
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.account_id = account_id
        self.session_factory = session_factory

        self._consumer = RedisStreamConsumer(
            stream_name=self.stream_name,
            group_name=self.group_name,
            consumer_name=self.consumer_name,
        )

        self._started = False

        # Case-insensitive broker symbol -> canonical AQE symbol.
        self._symbol_mapping: dict[str, str] = {}

        # Canonical symbols belonging to this account's enabled universe.
        self._canonical_symbols: set[str] = set()

        # Stream-health tracking.
        self._event_count = 0
        self._ignored_symbol_count = 0
        self._last_event_at: datetime | None = None
        self._last_event_symbol: str | None = None
        self._last_error: str | None = None
        self._last_error_at: datetime | None = None

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    async def start(self) -> None:
        """
        Load account symbol mappings and start consuming Redis messages.

        Repeated calls while running are safe.
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

        # Load mappings before accepting market-data messages.
        if self.account_id is not None:
            await self._load_symbol_mapping()

        await self._consumer.start(self._handle_message)

        self._started = True

        logger.info(
            "Market-data consumer started. "
            "stream=%s group=%s consumer=%s account_id=%s "
            "mapped_symbols=%d",
            self.stream_name,
            self.group_name,
            self.consumer_name,
            self.account_id,
            len(self._symbol_mapping),
        )

    async def stop(self) -> None:
        """Stop consuming market-data messages."""

        if not self._started:
            return

        await self._consumer.stop()

        self._started = False

        logger.info(
            "Market-data consumer stopped. "
            "stream=%s group=%s consumer=%s account_id=%s",
            self.stream_name,
            self.group_name,
            self.consumer_name,
            self.account_id,
        )

    # ==================================================================
    # SYMBOL MAPPING
    # ==================================================================

    async def _load_symbol_mapping(self) -> None:
        """
        Load enabled broker-symbol mappings for the runtime account.

        Mapping source:

            AccountSymbol.broker_symbol -> Symbol.name

        Broker symbol case is preserved in the database. Case-folding
        is used only for matching incoming symbol identifiers.

        Conflicting mappings are rejected rather than guessed.
        """

        if self.account_id is None:
            self._symbol_mapping.clear()
            self._canonical_symbols.clear()
            return

        statement = (
            select(
                AccountSymbol.broker_symbol,
                Symbol.name,
            )
            .join(
                Symbol,
                Symbol.id == AccountSymbol.symbol_id,
            )
            .where(
                AccountSymbol.account_id == self.account_id,
                AccountSymbol.enabled.is_(True),
            )
        )

        async with self.session_factory() as session:
            result = await session.execute(statement)
            rows = result.all()

        mapping: dict[str, str] = {}
        canonical_symbols: set[str] = set()

        for broker_symbol, canonical_symbol in rows:
            broker_name = (
                str(broker_symbol).strip() if broker_symbol is not None else ""
            )

            canonical_name = (
                str(canonical_symbol).strip().upper()
                if canonical_symbol is not None
                else ""
            )

            if not broker_name or not canonical_name:
                logger.warning(
                    "Ignoring incomplete account-symbol mapping. "
                    "account_id=%s broker_symbol=%r "
                    "canonical_symbol=%r",
                    self.account_id,
                    broker_symbol,
                    canonical_symbol,
                )
                continue

            broker_key = broker_name.casefold()
            existing = mapping.get(broker_key)

            if existing is not None and existing != canonical_name:
                raise ValueError(
                    "Conflicting broker-to-canonical symbol mappings "
                    f"for account_id={self.account_id}, "
                    f"broker_symbol={broker_name!r}: "
                    f"{existing!r} versus {canonical_name!r}."
                )

            mapping[broker_key] = canonical_name
            canonical_symbols.add(canonical_name.casefold())

        self._symbol_mapping = mapping
        self._canonical_symbols = canonical_symbols

        logger.info(
            "Loaded market-data symbol mappings. "
            "account_id=%s mapped_symbols=%d canonical_symbols=%d",
            self.account_id,
            len(mapping),
            len(canonical_symbols),
        )

        if not mapping:
            logger.warning(
                "No enabled symbol mappings found for runtime account %s. "
                "Unmapped market ticks will be ignored.",
                self.account_id,
            )

    def _resolve_symbol(self, incoming_symbol: str) -> str | None:
        """
        Resolve an incoming symbol to its canonical AQE identity.

        Broker-symbol mappings take precedence. Canonical symbols are
        also accepted when they belong to the active account's enabled
        symbol universe.

        No suffix removal or speculative symbol matching is performed.
        """

        symbol = incoming_symbol.strip()

        if not symbol:
            return None

        if self.account_id is None:
            # Preserve the previous standalone-consumer behavior.
            return symbol

        canonical = self._symbol_mapping.get(symbol.casefold())

        if canonical is not None:
            return canonical

        # Some upstream producers may already publish canonical names.
        # Accept them only when present in this account's known universe.
        if symbol.casefold() in self._canonical_symbols:
            return symbol.upper()

        return None

    # ==================================================================
    # STATUS
    # ==================================================================

    def status(self) -> dict[str, Any]:
        """
        Return a snapshot of consumer health.

        event_count counts successfully published MarketTickEvent
        instances. ignored_unmapped_symbols counts otherwise valid ticks
        ignored because their symbol is outside the configured account
        universe.
        """

        return {
            "running": self._started,
            "account_id": (
                str(self.account_id) if self.account_id is not None else None
            ),
            "mapped_symbols": len(self._symbol_mapping),
            "canonical_symbols": len(self._canonical_symbols),
            "event_count": self._event_count,
            "ignored_unmapped_symbols": self._ignored_symbol_count,
            "last_event_at": (
                self._last_event_at.isoformat()
                if self._last_event_at is not None
                else None
            ),
            "last_event_symbol": self._last_event_symbol,
            "last_error": self._last_error,
            "last_error_at": (
                self._last_error_at.isoformat()
                if self._last_error_at is not None
                else None
            ),
        }

    # ==================================================================
    # REDIS MESSAGE HANDLING
    # ==================================================================

    async def _handle_message(
        self,
        stream_name: str,
        message_id: str,
        fields: dict[str, Any],
    ) -> None:
        """
        Validate a Redis Stream envelope, normalize its MarketTick,
        and publish a MarketTickEvent to the shared AQE EventBus.

        Expected envelope:

            event_id
            event_type
            occurred_at
            payload

        The payload contains symbol, timestamp, bid, ask, and optional
        last/volume/volume_real fields.
        """

        logger.debug(
            "Received market-data message from Redis. " "stream=%s message_id=%s",
            stream_name,
            message_id,
        )

        try:
            # ----------------------------------------------------------
            # Event type
            # ----------------------------------------------------------

            event_type = fields.get("event_type")

            if event_type != self.EXPECTED_EVENT_TYPE:
                raise RedisMessageError(
                    "Unexpected market-data event type: "
                    f"{event_type!r}. "
                    f"Expected {self.EXPECTED_EVENT_TYPE!r}."
                )

            # ----------------------------------------------------------
            # Envelope
            # ----------------------------------------------------------

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

            # ----------------------------------------------------------
            # occurred_at
            # ----------------------------------------------------------

            try:
                occurred_at = datetime.fromisoformat(
                    str(occurred_at_raw).replace(
                        "Z",
                        "+00:00",
                    )
                )

                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(
                        tzinfo=timezone.utc,
                    )
                else:
                    occurred_at = occurred_at.astimezone(
                        timezone.utc,
                    )

            except (TypeError, ValueError) as exc:
                raise RedisMessageError(
                    "Market-data Redis message contains an invalid "
                    f"occurred_at value: {occurred_at_raw!r}"
                ) from exc

            # ----------------------------------------------------------
            # JSON payload
            # ----------------------------------------------------------

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
                    "Invalid market-data JSON. "
                    "stream=%s message_id=%s event_id=%s payload=%r",
                    stream_name,
                    message_id,
                    event_id,
                    payload_raw,
                )

                raise RedisMessageError(
                    "Market-data Redis message contains invalid JSON payload."
                ) from exc

            if not isinstance(payload, dict):
                raise RedisMessageError(
                    "Market-data Redis payload must be a JSON object."
                )

            # ----------------------------------------------------------
            # Required and optional payload fields
            # ----------------------------------------------------------

            symbol = payload.get("symbol")
            timestamp = payload.get("timestamp")
            bid = payload.get("bid")
            ask = payload.get("ask")

            last = payload.get("last", 0.0)
            volume = payload.get("volume", 0)
            volume_real = payload.get("volume_real", 0.0)

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
                raise RedisMessageError(
                    "Market-data Redis payload is missing required "
                    f"fields: {', '.join(missing_fields)}."
                )

            # ----------------------------------------------------------
            # Normalize and construct the MarketTick
            # ----------------------------------------------------------

            try:
                broker_symbol = str(symbol).strip()

                if not broker_symbol:
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

                canonical_symbol = self._resolve_symbol(
                    broker_symbol,
                )

                if canonical_symbol is None:
                    self._ignored_symbol_count += 1

                    logger.debug(
                        "Ignoring market tick outside the active "
                        "account's enabled symbol universe. "
                        "account_id=%s broker_symbol=%s "
                        "message_id=%s",
                        self.account_id,
                        broker_symbol,
                        message_id,
                    )

                    # This is a valid but irrelevant instrument, not a
                    # malformed Redis message. Do not retry it forever.
                    return

                tick = MarketTick(
                    symbol=canonical_symbol,
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
                    "Market-data payload could not be converted "
                    "to MarketTick. stream=%s message_id=%s "
                    "event_id=%s incoming_symbol=%r error=%s",
                    stream_name,
                    message_id,
                    event_id,
                    symbol,
                    exc,
                )

                raise RedisMessageError(
                    "Market-data Redis payload could not be converted "
                    f"into MarketTick: {exc}"
                ) from exc

            # ----------------------------------------------------------
            # Domain validation
            # ----------------------------------------------------------

            validation_errors = tick.validation_errors()

            if validation_errors:
                logger.error(
                    "Invalid MarketTick. "
                    "stream=%s message_id=%s event_id=%s "
                    "symbol=%s timestamp=%s bid=%s ask=%s "
                    "validation_errors=%s",
                    stream_name,
                    message_id,
                    event_id,
                    tick.symbol,
                    tick.timestamp,
                    tick.bid,
                    tick.ask,
                    validation_errors,
                )

                raise RedisMessageError(
                    f"Invalid MarketTick for {tick.symbol!r}: "
                    + "; ".join(validation_errors)
                )

            # ----------------------------------------------------------
            # Event creation and publication
            # ----------------------------------------------------------

            event = MarketTickEvent(
                event_id=event_id,
                occurred_at=occurred_at,
                tick=tick,
            )

            await event_bus.publish(event)

            # ----------------------------------------------------------
            # Health statistics
            # ----------------------------------------------------------

            self._event_count += 1
            self._last_event_at = datetime.now(timezone.utc)
            self._last_event_symbol = tick.symbol
            self._last_error = None
            self._last_error_at = None

            logger.debug(
                "MarketTickEvent published. "
                "message_id=%s event_id=%s "
                "broker_symbol=%s canonical_symbol=%s "
                "timestamp=%s bid=%s ask=%s",
                message_id,
                event.event_id,
                broker_symbol,
                tick.symbol,
                tick.timestamp,
                tick.bid,
                tick.ask,
            )

        except RedisMessageError as exc:
            self._last_error = str(exc)
            self._last_error_at = datetime.now(timezone.utc)
            raise

        except Exception as exc:
            logger.exception(
                "Failed to process market-data Redis message. "
                "stream=%s message_id=%s",
                stream_name,
                message_id,
            )

            self._last_error = str(exc)
            self._last_error_at = datetime.now(timezone.utc)

            raise RedisMessageError(
                "Market-data Redis message could not be processed."
            ) from exc

    # ==================================================================
    # VALUE PARSING
    # ==================================================================

    @staticmethod
    def _parse_timestamp(value: Any) -> int:
        """
        Convert a Redis payload timestamp into a positive Unix timestamp.
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
        """Convert a payload value to a finite float."""

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
