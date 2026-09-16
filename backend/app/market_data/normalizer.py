from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .models import MarketCandle, MarketTick


class MarketDataNormalizationError(Exception):
    """
    Raised when broker market-data cannot be normalized into
    an AQE-native MarketTick or MarketCandle.
    """

    pass


class MarketDataNormalizer:
    """
    Converts raw MT5 Bridge responses into AQE-native market-data models.

    Responsibilities
    ----------------
    - Validate broker response structure.
    - Normalize numeric values.
    - Normalize timestamps.
    - Construct MarketTick and MarketCandle objects.
    - Reject malformed or unsafe market data.

    This class contains no HTTP, Redis, database, or MT5-specific
    communication logic.

    Input
    -----
    Raw data returned by MT5BridgeService.

    Output
    ------
    MarketTick / MarketCandle.
    """

    # ==================================================================
    # TICK
    # ==================================================================

    def tick(
        self,
        *,
        data: Any,
        symbol: str,
    ) -> MarketTick:
        """
        Normalize one broker tick into an AQE MarketTick.

        Expected broker payload:

            {
                "symbol": "EURUSD",
                "timestamp": 1234567890,
                "bid": 1.1000,
                "ask": 1.1002,
                "last": 1.1001,
                "volume": 10,
                "volume_real": 10.0
            }

        The symbol supplied by the caller is authoritative because
        the bridge endpoint was requested for that symbol.
        """

        normalized_symbol = self._normalize_symbol(symbol)

        payload = self._normalize_mapping(data)

        timestamp = self._extract_timestamp(
            payload,
            field_names=("timestamp", "time"),
        )

        bid = self._extract_float(
            payload,
            field_name="bid",
            required=True,
        )

        ask = self._extract_float(
            payload,
            field_name="ask",
            required=True,
        )

        last = self._extract_float(
            payload,
            field_name="last",
            default=0.0,
        )

        volume = self._extract_int(
            payload,
            field_name="volume",
            default=0,
        )

        volume_real = self._extract_float(
            payload,
            field_name="volume_real",
            default=0.0,
        )

        tick = MarketTick(
            symbol=normalized_symbol,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            volume_real=volume_real,
        )

        errors = tick.validation_errors()

        if errors:
            raise MarketDataNormalizationError(
                "Invalid normalized MarketTick for "
                f"{normalized_symbol!r}: " + "; ".join(errors)
            )

        return tick

    # ==================================================================
    # CANDLES
    # ==================================================================

    def candles(
        self,
        *,
        data: Any,
        symbol: str,
        timeframe: str,
    ) -> list[MarketCandle]:
        """
        Normalize broker candle data into AQE MarketCandle objects.

        The bridge may return candles as:

            [
                {
                    "time": 1234567890,
                    "open": 1.0,
                    "high": 1.1,
                    "low": 0.9,
                    "close": 1.05,
                    "volume": 100,
                    "spread": 2,
                }
            ]

        or wrapped inside:

            {
                "candles": [...]
            }

        Both forms are supported.
        """

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_timeframe = self._normalize_timeframe(timeframe)

        records = self._normalize_candle_collection(data)

        result: list[MarketCandle] = []

        for index, record in enumerate(records):
            try:
                candle = self._normalize_candle(
                    record=record,
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                )

            except MarketDataNormalizationError as exc:
                raise MarketDataNormalizationError(
                    f"Failed to normalize candle at index {index} "
                    f"for {normalized_symbol!r} "
                    f"timeframe={normalized_timeframe!r}: {exc}"
                ) from exc

            result.append(candle)

        return result

    # ==================================================================
    # SINGLE CANDLE
    # ==================================================================

    def _normalize_candle(
        self,
        *,
        record: Any,
        symbol: str,
        timeframe: str,
    ) -> MarketCandle:
        payload = self._normalize_mapping(record)

        timestamp = self._extract_timestamp(
            payload,
            field_names=("timestamp", "time"),
        )

        open_price = self._extract_float(
            payload,
            field_name="open",
            required=True,
        )

        high_price = self._extract_float(
            payload,
            field_name="high",
            required=True,
        )

        low_price = self._extract_float(
            payload,
            field_name="low",
            required=True,
        )

        close_price = self._extract_float(
            payload,
            field_name="close",
            required=True,
        )

        volume = self._extract_int(
            payload,
            field_name="volume",
            default=0,
            aliases=("tick_volume",),
        )

        spread = self._extract_int(
            payload,
            field_name="spread",
            default=0,
        )

        candle = MarketCandle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            spread=spread,
        )

        errors = candle.validation_errors()

        if errors:
            raise MarketDataNormalizationError(
                "Invalid normalized MarketCandle: " + "; ".join(errors)
            )

        return candle

    # ==================================================================
    # SYMBOL
    # ==================================================================

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        if not isinstance(symbol, str):
            raise MarketDataNormalizationError("Symbol must be a string.")

        normalized = symbol.strip()

        if not normalized:
            raise MarketDataNormalizationError("Symbol cannot be empty.")

        return normalized

    @staticmethod
    def _normalize_timeframe(timeframe: Any) -> str:
        if not isinstance(timeframe, str):
            raise MarketDataNormalizationError("Timeframe must be a string.")

        normalized = timeframe.strip().upper()

        if not normalized:
            raise MarketDataNormalizationError("Timeframe cannot be empty.")

        return normalized

    # ==================================================================
    # MAPPING
    # ==================================================================

    @staticmethod
    def _normalize_mapping(data: Any) -> dict[str, Any]:
        """
        Convert a broker response into a dictionary.

        Supports:

        - dict
        - objects exposing model_dump()
        - objects exposing _asdict()
        """

        if isinstance(data, dict):
            return dict(data)

        model_dump = getattr(data, "model_dump", None)

        if callable(model_dump):
            try:
                result = model_dump()

            except Exception as exc:
                raise MarketDataNormalizationError(
                    "Failed to convert broker response using model_dump()."
                ) from exc

            if isinstance(result, dict):
                return dict(result)

        asdict = getattr(data, "_asdict", None)

        if callable(asdict):
            try:
                result = asdict()

            except Exception as exc:
                raise MarketDataNormalizationError(
                    "Failed to convert broker response using _asdict()."
                ) from exc

            if isinstance(result, dict):
                return dict(result)

        raise MarketDataNormalizationError(
            "Broker market-data response must be a mapping or "
            "an object exposing model_dump() or _asdict()."
        )

    # ==================================================================
    # CANDLE COLLECTION
    # ==================================================================

    @classmethod
    def _normalize_candle_collection(
        cls,
        data: Any,
    ) -> list[Any]:
        """
        Normalize the different candle response shapes supported
        by the Bridge.
        """

        if isinstance(data, dict):
            if "candles" in data:
                data = data["candles"]

            elif "data" in data:
                data = data["data"]

            else:
                raise MarketDataNormalizationError(
                    "Candle response dictionary does not contain "
                    "'candles' or 'data'."
                )

        if data is None:
            raise MarketDataNormalizationError("Candle response is empty.")

        if isinstance(data, (str, bytes, bytearray)):
            raise MarketDataNormalizationError(
                "Candle response must be a collection of candle records."
            )

        try:
            records = list(data)

        except TypeError as exc:
            raise MarketDataNormalizationError(
                "Candle response is not iterable."
            ) from exc

        return records

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @classmethod
    def _extract_timestamp(
        cls,
        payload: dict[str, Any],
        *,
        field_names: tuple[str, ...],
    ) -> int:
        """
        Extract and normalize a Unix timestamp.

        Supported values:

        - int
        - float
        - numeric string
        - datetime
        - ISO datetime string
        """

        value = cls._first_present(
            payload,
            field_names,
        )

        if value is None:
            raise MarketDataNormalizationError(
                f"Missing timestamp field. Expected one of: "
                f"{', '.join(field_names)}."
            )

        if isinstance(value, bool):
            raise MarketDataNormalizationError("Timestamp must not be boolean.")

        if isinstance(value, datetime):
            return cls._datetime_to_timestamp(value)

        if isinstance(value, int):
            timestamp = value

        elif isinstance(value, float):
            if not math.isfinite(value):
                raise MarketDataNormalizationError(
                    f"Timestamp must be finite, got {value!r}."
                )

            timestamp = int(value)

        elif isinstance(value, str):
            raw = value.strip()

            if not raw:
                raise MarketDataNormalizationError("Timestamp must not be empty.")

            timestamp = cls._parse_timestamp_string(raw)

        else:
            raise MarketDataNormalizationError(
                "Timestamp must be an integer-compatible value, "
                "datetime, or ISO datetime string; "
                f"got {type(value).__name__}."
            )

        if timestamp <= 0:
            raise MarketDataNormalizationError(
                f"Timestamp must be greater than 0, got {timestamp}."
            )

        return timestamp

    @staticmethod
    def _datetime_to_timestamp(value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        timestamp = int(value.timestamp())

        if timestamp <= 0:
            raise MarketDataNormalizationError(
                f"Timestamp must be greater than 0, got {timestamp}."
            )

        return timestamp

    @classmethod
    def _parse_timestamp_string(
        cls,
        value: str,
    ) -> int:
        """
        Parse either a numeric timestamp or an ISO datetime.
        """

        try:
            numeric = float(value)

        except ValueError:
            numeric = None

        if numeric is not None:
            if not math.isfinite(numeric):
                raise MarketDataNormalizationError(
                    f"Timestamp must be finite, got {value!r}."
                )

            return int(numeric)

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

        except ValueError as exc:
            raise MarketDataNormalizationError(
                f"Invalid timestamp value: {value!r}."
            ) from exc

        return cls._datetime_to_timestamp(parsed)

    # ==================================================================
    # FLOAT
    # ==================================================================

    @classmethod
    def _extract_float(
        cls,
        payload: dict[str, Any],
        *,
        field_name: str,
        default: float | None = None,
        required: bool = False,
    ) -> float:
        value = payload.get(field_name)

        if value is None:
            if required:
                raise MarketDataNormalizationError(
                    f"Missing required field: {field_name}."
                )

            if default is None:
                raise MarketDataNormalizationError(f"Missing field: {field_name}.")

            return default

        if isinstance(value, bool):
            raise MarketDataNormalizationError(f"{field_name} must not be boolean.")

        try:
            result = float(value)

        except (TypeError, ValueError, OverflowError) as exc:
            raise MarketDataNormalizationError(
                f"{field_name} is not a valid number: {value!r}."
            ) from exc

        if not math.isfinite(result):
            raise MarketDataNormalizationError(
                f"{field_name} must be finite, got {value!r}."
            )

        return result

    # ==================================================================
    # INTEGER
    # ==================================================================

    @classmethod
    def _extract_int(
        cls,
        payload: dict[str, Any],
        *,
        field_name: str,
        default: int | None = None,
        aliases: tuple[str, ...] = (),
    ) -> int:
        value = cls._first_present(
            payload,
            (field_name, *aliases),
        )

        if value is None:
            if default is None:
                raise MarketDataNormalizationError(f"Missing field: {field_name}.")

            return default

        if isinstance(value, bool):
            raise MarketDataNormalizationError(f"{field_name} must not be boolean.")

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if not math.isfinite(value):
                raise MarketDataNormalizationError(
                    f"{field_name} must be finite, got {value!r}."
                )

            if not value.is_integer():
                raise MarketDataNormalizationError(
                    f"{field_name} must be an integer, got {value!r}."
                )

            return int(value)

        if isinstance(value, str):
            raw = value.strip()

            if not raw:
                raise MarketDataNormalizationError(f"{field_name} must not be empty.")

            try:
                numeric = float(raw)

            except ValueError as exc:
                raise MarketDataNormalizationError(
                    f"{field_name} is not a valid integer: {value!r}."
                ) from exc

            if not math.isfinite(numeric):
                raise MarketDataNormalizationError(
                    f"{field_name} must be finite, got {value!r}."
                )

            if not numeric.is_integer():
                raise MarketDataNormalizationError(
                    f"{field_name} must be an integer, got {value!r}."
                )

            return int(numeric)

        raise MarketDataNormalizationError(
            f"{field_name} must be integer-compatible, " f"got {type(value).__name__}."
        )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _first_present(
        payload: dict[str, Any],
        field_names: tuple[str, ...],
    ) -> Any:
        for field_name in field_names:
            if field_name in payload:
                return payload[field_name]

        return None
