"""General-purpose helper utilities for the Athena Quant Engine.

This module contains small, reusable functions that are not specific to
any AQE subsystem.

Business logic should remain inside the appropriate subsystem rather
than being placed here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, TypeVar
from uuid import UUID

T = TypeVar("T")


# ============================================================================
# Numeric helpers
# ============================================================================


def to_decimal(
    value: int | float | str | Decimal,
    *,
    default: Decimal | None = None,
) -> Decimal:
    """Convert a value to Decimal safely.

    Args:
        value: Numeric value to convert.
        default: Value returned if conversion fails.

    Returns:
        Decimal representation of the value.

    Raises:
        ValueError: If conversion fails and no default is provided.
    """

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        if default is not None:
            return default

        raise ValueError(f"Unable to convert {value!r} to Decimal.") from exc


def round_decimal(
    value: int | float | str | Decimal,
    decimals: int = 2,
    *,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    """Round a numeric value using Decimal arithmetic.

    This is preferable to relying on binary floating-point rounding for
    financial values.

    Args:
        value: Value to round.
        decimals: Number of decimal places.
        rounding: Decimal rounding mode.

    Returns:
        Rounded Decimal value.
    """

    if decimals < 0:
        raise ValueError("decimals must be greater than or equal to zero.")

    decimal_value = to_decimal(value)

    quantizer = Decimal("1").scaleb(-decimals)

    return decimal_value.quantize(
        quantizer,
        rounding=rounding,
    )


def floor_to_step(
    value: int | float | str | Decimal,
    step: int | float | str | Decimal,
) -> Decimal:
    """Round a value down to the nearest step.

    Useful for broker volume steps such as:

        0.01
        0.10
        1.00

    Example:
        floor_to_step(0.137, 0.01) -> Decimal("0.13")
    """

    value_decimal = to_decimal(value)
    step_decimal = to_decimal(step)

    if step_decimal <= 0:
        raise ValueError("step must be greater than zero.")

    steps = (value_decimal / step_decimal).to_integral_value(
        rounding=ROUND_DOWN,
    )

    return steps * step_decimal


def clamp(
    value: T,
    minimum: T,
    maximum: T,
) -> T:
    """Clamp a comparable value to a minimum/maximum range."""

    if minimum > maximum:
        raise ValueError("minimum cannot be greater than maximum.")

    return max(
        minimum,
        min(value, maximum),
    )


def is_finite_number(
    value: int | float | Decimal,
) -> bool:
    """Return whether a numeric value is finite."""

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


# ============================================================================
# Percentage helpers
# ============================================================================


def percentage_change(
    old_value: int | float | Decimal,
    new_value: int | float | Decimal,
) -> Decimal:
    """Calculate percentage change from old value to new value.

    Returns:
        Percentage change expressed as a percentage.

    Example:
        percentage_change(100, 110) -> Decimal("10")
    """

    old_decimal = to_decimal(old_value)
    new_decimal = to_decimal(new_value)

    if old_decimal == 0:
        raise ZeroDivisionError("Cannot calculate percentage change from zero.")

    return ((new_decimal - old_decimal) / old_decimal) * Decimal("100")


def percentage_of(
    value: int | float | Decimal,
    percentage: int | float | Decimal,
) -> Decimal:
    """Calculate a percentage of a value.

    Example:
        percentage_of(10000, 1.5) -> Decimal("150")
    """

    return to_decimal(value) * to_decimal(percentage) / Decimal("100")


# ============================================================================
# String helpers
# ============================================================================


def normalize_string(
    value: str,
    *,
    lowercase: bool = True,
    strip: bool = True,
) -> str:
    """Normalize a string for consistent internal use."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")

    result = value

    if strip:
        result = result.strip()

    if lowercase:
        result = result.lower()

    return result


def normalize_symbol(
    symbol: str,
) -> str:
    """Normalize a trading symbol.

    Examples:

        " eurusd " -> "EURUSD"
        "BTC/USD" -> "BTC/USD"
    """

    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string.")

    return symbol.strip().upper()


def snake_case(
    value: str,
) -> str:
    """Convert a string to snake_case."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")

    value = value.strip()

    value = re.sub(
        r"([A-Z]+)([A-Z][a-z])",
        r"\1_\2",
        value,
    )

    value = re.sub(
        r"([a-z\d])([A-Z])",
        r"\1_\2",
        value,
    )

    value = re.sub(
        r"[\s\-]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    return value.lower().strip("_")


# ============================================================================
# Collection helpers
# ============================================================================


def chunked(
    items: Sequence[T],
    size: int,
) -> list[list[T]]:
    """Split a sequence into fixed-size chunks."""

    if size <= 0:
        raise ValueError("size must be greater than zero.")

    return [
        list(items[index : index + size])
        for index in range(
            0,
            len(items),
            size,
        )
    ]


def unique_preserve_order(
    items: Iterable[T],
) -> list[T]:
    """Return unique items while preserving their original order."""

    seen: set[T] = set()
    result: list[T] = []

    for item in items:
        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def get_nested(
    data: Mapping[str, Any],
    path: str,
    *,
    default: T | None = None,
) -> Any | T | None:
    """Safely retrieve a nested mapping value.

    Example:

        get_nested(
            {"broker": {"mt5": {"enabled": True}}},
            "broker.mt5.enabled",
        )

        -> True
    """

    current: Any = data

    for key in path.split("."):
        if not isinstance(current, Mapping):
            return default

        if key not in current:
            return default

        current = current[key]

    return current


# ============================================================================
# Dictionary helpers
# ============================================================================


def remove_none(
    data: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a dictionary with None values removed."""

    return {key: value for key, value in data.items() if value is not None}


def merge_dicts(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    """Recursively merge two dictionaries.

    Values from ``override`` take precedence.
    Nested mappings are merged recursively.
    """

    result = dict(base)

    for key, value in override.items():
        existing = result.get(key)

        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = merge_dicts(
                existing,
                value,
            )
        else:
            result[key] = value

    return result


# ============================================================================
# Date/time helpers
# ============================================================================


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)


def ensure_utc(
    value: datetime,
) -> datetime:
    """Ensure a datetime is timezone-aware and represented in UTC.

    Naive datetimes are interpreted as UTC.
    """

    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime.")

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc,
        )

    return value.astimezone(timezone.utc)


def to_timestamp(
    value: datetime,
) -> float:
    """Convert a datetime to a Unix timestamp."""

    return ensure_utc(value).timestamp()


def from_timestamp(
    timestamp: int | float,
) -> datetime:
    """Convert a Unix timestamp into a UTC datetime."""

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


def start_of_day(
    value: datetime | date,
) -> datetime:
    """Return the start of the UTC day."""

    if isinstance(value, datetime):
        value = ensure_utc(value).date()

    return datetime.combine(
        value,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def end_of_day(
    value: datetime | date,
) -> datetime:
    """Return the end of the UTC day."""

    return start_of_day(value) + timedelta(
        days=1,
        microseconds=-1,
    )


# ============================================================================
# UUID helpers
# ============================================================================


def to_uuid(
    value: UUID | str,
) -> UUID:
    """Convert a UUID or UUID string to UUID."""

    if isinstance(value, UUID):
        return value

    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid UUID value: {value!r}") from exc


# ============================================================================
# Serialization helpers
# ============================================================================


def serialize_value(
    value: Any,
) -> Any:
    """Convert common AQE values into JSON-friendly values.

    This helper intentionally handles only common infrastructure types.
    Domain-specific serialization should remain in the relevant module.
    """

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {str(key): serialize_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [serialize_value(item) for item in value]

    if hasattr(value, "value"):
        return serialize_value(value.value)

    return value


# ============================================================================
# Retry helpers
# ============================================================================


def calculate_backoff(
    attempt: int,
    *,
    base_delay: float = 1.0,
    maximum_delay: float = 60.0,
    multiplier: float = 2.0,
) -> float:
    """Calculate exponential retry backoff.

    Example:

        attempt 0 -> 1 second
        attempt 1 -> 2 seconds
        attempt 2 -> 4 seconds
        attempt 3 -> 8 seconds

    The result is capped by ``maximum_delay``.
    """

    if attempt < 0:
        raise ValueError("attempt cannot be negative.")

    if base_delay < 0:
        raise ValueError("base_delay cannot be negative.")

    if maximum_delay < 0:
        raise ValueError("maximum_delay cannot be negative.")

    if multiplier <= 0:
        raise ValueError("multiplier must be greater than zero.")

    delay = base_delay * (multiplier**attempt)

    return min(
        delay,
        maximum_delay,
    )


__all__ = [
    "calculate_backoff",
    "chunked",
    "clamp",
    "end_of_day",
    "ensure_utc",
    "floor_to_step",
    "from_timestamp",
    "get_nested",
    "is_finite_number",
    "merge_dicts",
    "normalize_string",
    "normalize_symbol",
    "percentage_change",
    "percentage_of",
    "remove_none",
    "round_decimal",
    "serialize_value",
    "snake_case",
    "start_of_day",
    "to_decimal",
    "to_timestamp",
    "to_uuid",
    "unique_preserve_order",
    "utc_now",
]
