"""Centralized logging utilities for the Athena Quant Engine.

This module provides consistent logging configuration across all AQE
subsystems.

The logger is designed to work in development, testing, Docker, and
production environments without requiring individual modules to configure
their own logging handlers.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================================
# Constants
# ============================================================================

DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | " "%(name)s | %(message)s"

DEFAULT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

AQE_LOGGER_NAME = "aqe"


# ============================================================================
# Context
# ============================================================================


class AQEContextFilter(logging.Filter):
    """Inject standard AQE context into log records."""

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        """Ensure standard context fields exist."""

        if not hasattr(record, "component"):
            record.component = "unknown"

        if not hasattr(record, "event_id"):
            record.event_id = None

        if not hasattr(record, "correlation_id"):
            record.correlation_id = None

        return True


# ============================================================================
# JSON Formatter
# ============================================================================


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        """Convert a log record into a JSON object."""

        payload: dict[str, Any] = {
            "timestamp": datetime.now(
                timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "component": getattr(
                record,
                "component",
                None,
            ),
            "event_id": getattr(
                record,
                "event_id",
                None,
            ),
            "correlation_id": getattr(
                record,
                "correlation_id",
                None,
            ),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info,
            )

        return json.dumps(
            payload,
            default=str,
        )


# ============================================================================
# Logger Creation
# ============================================================================


def get_logger(
    name: str | None = None,
) -> logging.Logger:
    """Return an AQE logger.

    Args:
        name: Optional logger name.

    Returns:
        Configured logging.Logger instance.

    Example:

        logger = get_logger(__name__)
        logger.info("Risk engine started.")
    """

    if name is None:
        return logging.getLogger(AQE_LOGGER_NAME)

    if name.startswith(AQE_LOGGER_NAME):
        return logging.getLogger(name)

    return logging.getLogger(
        f"{AQE_LOGGER_NAME}.{name}",
    )


# ============================================================================
# Logging Configuration
# ============================================================================


def configure_logging(
    *,
    level: int | str = DEFAULT_LOG_LEVEL,
    log_file: str | Path | None = None,
    json_format: bool = False,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configure centralized AQE logging.

    Args:
        level:
            Logging level such as ``DEBUG``, ``INFO``, ``WARNING``,
            ``ERROR``, or ``CRITICAL``.

        log_file:
            Optional path for file logging.

        json_format:
            If True, logs are emitted as JSON.

        console:
            If True, logs are written to stdout.

        max_bytes:
            Maximum size of a log file before rotation.

        backup_count:
            Number of rotated log files to retain.

    Returns:
        The root AQE logger.
    """

    logger = logging.getLogger(AQE_LOGGER_NAME)

    if isinstance(level, str):
        level = getattr(
            logging,
            level.upper(),
            None,
        )

        if not isinstance(level, int):
            raise ValueError(f"Invalid logging level: {level!r}")

    logger.setLevel(level)

    logger.propagate = False

    # ------------------------------------------------------------------
    # Remove existing AQE handlers.
    # ------------------------------------------------------------------

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # ------------------------------------------------------------------
    # Formatter.
    # ------------------------------------------------------------------

    if json_format:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt=DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_DATE_FORMAT,
        )

    # ------------------------------------------------------------------
    # Context filter.
    # ------------------------------------------------------------------

    context_filter = AQEContextFilter()

    # ------------------------------------------------------------------
    # Console handler.
    # ------------------------------------------------------------------

    if console:
        console_handler = logging.StreamHandler(
            sys.stdout,
        )

        console_handler.setLevel(level)

        console_handler.setFormatter(
            formatter,
        )

        console_handler.addFilter(
            context_filter,
        )

        logger.addHandler(
            console_handler,
        )

    # ------------------------------------------------------------------
    # File handler.
    # ------------------------------------------------------------------

    if log_file is not None:
        log_path = Path(log_file)

        log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )

        file_handler.setLevel(level)

        file_handler.setFormatter(
            formatter,
        )

        file_handler.addFilter(
            context_filter,
        )

        logger.addHandler(
            file_handler,
        )

    logger.info(
        "AQE logging configured.",
    )

    return logger


# ============================================================================
# Component Logger
# ============================================================================


def get_component_logger(
    component: str,
) -> logging.Logger:
    """Return a logger for a specific AQE component.

    Example:

        logger = get_component_logger("risk")
        logger.info("Risk manager started.")

    Produces a logger named:

        aqe.risk
    """

    if not component:
        raise ValueError(
            "component cannot be empty.",
        )

    return get_logger(
        component.strip(),
    )


# ============================================================================
# Context Logger Adapter
# ============================================================================


class AQELoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that carries AQE execution context."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        component: str | None = None,
        event_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        extra = {
            "component": component,
            "event_id": event_id,
            "correlation_id": correlation_id,
        }

        super().__init__(
            logger,
            extra,
        )

    def process(
        self,
        msg: Any,
        kwargs: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        """Inject AQE context into the logging call."""

        extra = kwargs.setdefault(
            "extra",
            {},
        )

        extra.setdefault(
            "component",
            self.extra.get("component"),
        )

        extra.setdefault(
            "event_id",
            self.extra.get("event_id"),
        )

        extra.setdefault(
            "correlation_id",
            self.extra.get("correlation_id"),
        )

        return msg, kwargs


def get_context_logger(
    component: str,
    *,
    event_id: str | None = None,
    correlation_id: str | None = None,
) -> AQELoggerAdapter:
    """Create a context-aware AQE logger.

    Example:

        logger = get_context_logger(
            "execution",
            event_id="123",
            correlation_id="456",
        )

        logger.info("Order executed.")
    """

    return AQELoggerAdapter(
        get_component_logger(component),
        component=component,
        event_id=event_id,
        correlation_id=correlation_id,
    )


# ============================================================================
# Utility Functions
# ============================================================================


def set_log_level(
    level: int | str,
) -> None:
    """Change the AQE logger level."""

    if isinstance(level, str):
        level_value = getattr(
            logging,
            level.upper(),
            None,
        )

        if not isinstance(level_value, int):
            raise ValueError(f"Invalid logging level: {level!r}")

        level = level_value

    logging.getLogger(
        AQE_LOGGER_NAME,
    ).setLevel(level)


def get_log_level() -> int:
    """Return the current AQE logging level."""

    return logging.getLogger(
        AQE_LOGGER_NAME,
    ).level


def shutdown_logging() -> None:
    """Flush and shut down AQE logging handlers."""

    logger = logging.getLogger(
        AQE_LOGGER_NAME,
    )

    for handler in list(logger.handlers):
        handler.flush()
        handler.close()

    logging.shutdown()


__all__ = [
    "AQEContextFilter",
    "AQELoggerAdapter",
    "AQE_LOGGER_NAME",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_DATE_FORMAT",
    "JSONFormatter",
    "configure_logging",
    "get_component_logger",
    "get_context_logger",
    "get_log_level",
    "get_logger",
    "set_log_level",
    "shutdown_logging",
]
