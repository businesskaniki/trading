"""Reusable validation utilities for the Athena Quant Engine.

This module contains generic validation functions shared across AQE
subsystems.

Domain-specific business rules should remain in their respective
subsystems, for example:

    engine/risk/
    engine/execution/
    engine/strategy/
    engine/broker/

These validators should remain deterministic, lightweight, and free of
external I/O.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from engine.utils.exceptions import (
    InvalidRangeError,
    InvalidValueError,
    RequiredFieldError,
)

T = TypeVar("T")


# ============================================================================
# Generic validation
# ============================================================================


def validate_required(
    value: T | None,
    field_name: str,
) -> T:
    """Validate that a required value exists.

    Args:
        value: Value to validate.
        field_name: Name used in the error message.

    Returns:
        The original value.

    Raises:
        RequiredFieldError: If the value is None or an empty string.
    """

    if value is None:
        raise RequiredFieldError(
            f"{field_name} is required.",
            details={"field": field_name},
        )

    if isinstance(value, str) and not value.strip():
        raise RequiredFieldError(
            f"{field_name} cannot be empty.",
            details={"field": field_name},
        )

    return value


def validate_type(
    value: Any,
    expected_type: type[T] | tuple[type[Any], ...],
    field_name: str = "value",
) -> T:
    """Validate that a value has the expected type."""

    if not isinstance(value, expected_type):
        raise InvalidValueError(
            f"{field_name} must be of type " f"{_type_name(expected_type)}.",
            details={
                "field": field_name,
                "expected_type": _type_name(expected_type),
                "actual_type": type(value).__name__,
            },
        )

    return value


def validate_choices(
    value: T,
    choices: Iterable[T],
    field_name: str = "value",
) -> T:
    """Validate that a value belongs to an allowed set."""

    choices = tuple(choices)

    if value not in choices:
        raise InvalidValueError(
            f"{field_name} must be one of {choices!r}.",
            details={
                "field": field_name,
                "value": value,
                "choices": choices,
            },
        )

    return value


# ============================================================================
# Numeric validation
# ============================================================================


def validate_numeric(
    value: Any,
    field_name: str = "value",
) -> int | float | Decimal:
    """Validate that a value is numeric and finite."""

    if isinstance(value, bool):
        raise InvalidValueError(
            f"{field_name} must be numeric.",
            details={"field": field_name},
        )

    if not isinstance(
        value,
        (int, float, Decimal),
    ):
        raise InvalidValueError(
            f"{field_name} must be numeric.",
            details={
                "field": field_name,
                "actual_type": type(value).__name__,
            },
        )

    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidValueError(
            f"{field_name} must be finite.",
            details={"field": field_name},
        )

    return value


def validate_positive(
    value: int | float | Decimal,
    field_name: str = "value",
) -> int | float | Decimal:
    """Validate that a numeric value is greater than zero."""

    validate_numeric(
        value,
        field_name,
    )

    if value <= 0:
        raise InvalidValueError(
            f"{field_name} must be greater than zero.",
            details={
                "field": field_name,
                "value": value,
            },
        )

    return value


def validate_non_negative(
    value: int | float | Decimal,
    field_name: str = "value",
) -> int | float | Decimal:
    """Validate that a numeric value is zero or greater."""

    validate_numeric(
        value,
        field_name,
    )

    if value < 0:
        raise InvalidValueError(
            f"{field_name} cannot be negative.",
            details={
                "field": field_name,
                "value": value,
            },
        )

    return value


def validate_range(
    value: int | float | Decimal,
    minimum: int | float | Decimal,
    maximum: int | float | Decimal,
    field_name: str = "value",
) -> int | float | Decimal:
    """Validate that a numeric value is within an inclusive range."""

    validate_numeric(
        value,
        field_name,
    )

    if minimum > maximum:
        raise InvalidRangeError(
            "Minimum cannot be greater than maximum.",
            details={
                "minimum": minimum,
                "maximum": maximum,
            },
        )

    if value < minimum or value > maximum:
        raise InvalidRangeError(
            f"{field_name} must be between " f"{minimum} and {maximum}.",
            details={
                "field": field_name,
                "value": value,
                "minimum": minimum,
                "maximum": maximum,
            },
        )

    return value


def validate_percentage(
    value: int | float | Decimal,
    field_name: str = "percentage",
) -> int | float | Decimal:
    """Validate a percentage expressed from 0 to 100."""

    return validate_range(
        value,
        0,
        100,
        field_name,
    )


def validate_positive_percentage(
    value: int | float | Decimal,
    field_name: str = "percentage",
) -> int | float | Decimal:
    """Validate a percentage greater than zero and at most 100."""

    validate_numeric(
        value,
        field_name,
    )

    if value <= 0 or value > 100:
        raise InvalidRangeError(
            f"{field_name} must be greater than 0 and " f"less than or equal to 100.",
            details={
                "field": field_name,
                "value": value,
                "minimum": 0,
                "maximum": 100,
            },
        )

    return value


# ============================================================================
# Trading-specific primitive validation
# ============================================================================


def validate_price(
    price: int | float | Decimal,
    field_name: str = "price",
) -> int | float | Decimal:
    """Validate that a trading price is positive."""

    return validate_positive(
        price,
        field_name,
    )


def validate_quantity(
    quantity: int | float | Decimal,
    field_name: str = "quantity",
) -> int | float | Decimal:
    """Validate that an order quantity is positive."""

    return validate_positive(
        quantity,
        field_name,
    )


def validate_volume(
    volume: int | float | Decimal,
    field_name: str = "volume",
) -> int | float | Decimal:
    """Validate that a trading volume is positive."""

    return validate_positive(
        volume,
        field_name,
    )


def validate_step(
    value: int | float | Decimal,
    step: int | float | Decimal,
    field_name: str = "value",
) -> int | float | Decimal:
    """Validate that a value conforms to a positive step size.

    Example:

        validate_step(0.10, 0.01)

    is valid.

    ``validate_step`` uses Decimal arithmetic internally to reduce
    floating-point precision problems.
    """

    validate_positive(
        value,
        field_name,
    )

    validate_positive(
        step,
        "step",
    )

    value_decimal = Decimal(str(value))
    step_decimal = Decimal(str(step))

    remainder = value_decimal % step_decimal

    if remainder != 0:
        raise InvalidValueError(
            f"{field_name} must be a multiple of {step}.",
            details={
                "field": field_name,
                "value": str(value),
                "step": str(step),
            },
        )

    return value


# ============================================================================
# Symbol validation
# ============================================================================


_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/\-]{0,31}$")


def validate_symbol(
    symbol: str,
    field_name: str = "symbol",
) -> str:
    """Validate a trading symbol.

    Examples of valid symbols:

        EURUSD
        BTCUSD
        EUR/USD
        XAUUSD
        US30
        BTC-USDT
    """

    validate_required(
        symbol,
        field_name,
    )

    normalized = symbol.strip().upper()

    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise InvalidValueError(
            f"Invalid trading symbol: {symbol!r}.",
            details={
                "field": field_name,
                "value": symbol,
            },
        )

    return normalized


# ============================================================================
# Timeframe validation
# ============================================================================


_VALID_TIMEFRAMES = frozenset(
    {
        "1m",
        "2m",
        "3m",
        "5m",
        "10m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    }
)


def validate_timeframe(
    timeframe: str,
    field_name: str = "timeframe",
) -> str:
    """Validate a supported market timeframe."""

    validate_required(
        timeframe,
        field_name,
    )

    if timeframe not in _VALID_TIMEFRAMES:
        raise InvalidValueError(
            f"Unsupported timeframe: {timeframe!r}.",
            details={
                "field": field_name,
                "value": timeframe,
                "supported": sorted(
                    _VALID_TIMEFRAMES,
                ),
            },
        )

    return timeframe


# ============================================================================
# UUID validation
# ============================================================================


def validate_uuid(
    value: UUID | str,
    field_name: str = "id",
) -> UUID:
    """Validate and normalize a UUID."""

    validate_required(
        value,
        field_name,
    )

    if isinstance(value, UUID):
        return value

    if not isinstance(value, str):
        raise InvalidValueError(
            f"{field_name} must be a UUID.",
            details={
                "field": field_name,
                "value": value,
            },
        )

    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidValueError(
            f"{field_name} must contain a valid UUID.",
            details={
                "field": field_name,
                "value": value,
            },
        ) from exc


# ============================================================================
# Date/time validation
# ============================================================================


def validate_datetime(
    value: datetime,
    field_name: str = "datetime",
) -> datetime:
    """Validate a datetime value."""

    if not isinstance(value, datetime):
        raise InvalidValueError(
            f"{field_name} must be a datetime.",
            details={
                "field": field_name,
                "actual_type": type(value).__name__,
            },
        )

    return value


def validate_date(
    value: date,
    field_name: str = "date",
) -> date:
    """Validate a date value."""

    if not isinstance(value, date):
        raise InvalidValueError(
            f"{field_name} must be a date.",
            details={
                "field": field_name,
                "actual_type": type(value).__name__,
            },
        )

    return value


def validate_datetime_range(
    start: datetime,
    end: datetime,
) -> tuple[datetime, datetime]:
    """Validate that a datetime range is logically ordered."""

    validate_datetime(
        start,
        "start",
    )

    validate_datetime(
        end,
        "end",
    )

    if start > end:
        raise InvalidRangeError(
            "Start datetime cannot be after end datetime.",
            details={
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    return start, end


# ============================================================================
# Collection validation
# ============================================================================


def validate_not_empty(
    value: Iterable[T],
    field_name: str = "value",
) -> Iterable[T]:
    """Validate that an iterable contains at least one item."""

    if isinstance(value, (str, bytes)):
        if not value:
            raise RequiredFieldError(
                f"{field_name} cannot be empty.",
                details={"field": field_name},
            )

        return value

    try:
        if len(value):  # type: ignore[arg-type]
            return value
    except TypeError:
        items = list(value)

        if items:
            return items

    raise RequiredFieldError(
        f"{field_name} cannot be empty.",
        details={"field": field_name},
    )


def validate_list_length(
    value: list[Any] | tuple[Any, ...],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    field_name: str = "value",
) -> list[Any] | tuple[Any, ...]:
    """Validate the length of a list or tuple."""

    if minimum is not None and minimum < 0:
        raise InvalidRangeError(
            "minimum cannot be negative.",
        )

    if maximum is not None and maximum < 0:
        raise InvalidRangeError(
            "maximum cannot be negative.",
        )

    if minimum is not None and maximum is not None and minimum > maximum:
        raise InvalidRangeError(
            "minimum cannot be greater than maximum.",
        )

    length = len(value)

    if minimum is not None and length < minimum:
        raise InvalidRangeError(
            f"{field_name} must contain at least " f"{minimum} items.",
            details={
                "field": field_name,
                "length": length,
                "minimum": minimum,
            },
        )

    if maximum is not None and length > maximum:
        raise InvalidRangeError(
            f"{field_name} must contain at most " f"{maximum} items.",
            details={
                "field": field_name,
                "length": length,
                "maximum": maximum,
            },
        )

    return value


# ============================================================================
# Internal helpers
# ============================================================================


def _type_name(
    expected_type: type[Any] | tuple[type[Any], ...],
) -> str:
    """Return a readable type name."""

    if isinstance(expected_type, tuple):
        return " | ".join(item.__name__ for item in expected_type)

    return expected_type.__name__


__all__ = [
    "validate_required",
    "validate_type",
    "validate_choices",
    "validate_numeric",
    "validate_positive",
    "validate_non_negative",
    "validate_range",
    "validate_percentage",
    "validate_positive_percentage",
    "validate_price",
    "validate_quantity",
    "validate_volume",
    "validate_step",
    "validate_symbol",
    "validate_timeframe",
    "validate_uuid",
    "validate_datetime",
    "validate_date",
    "validate_datetime_range",
    "validate_not_empty",
    "validate_list_length",
]
