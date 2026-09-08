from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    """
    Read a boolean environment variable safely.
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True, slots=True)
class RedisConfig:
    """
    Runtime configuration for AQE Redis infrastructure.

    Redis DB 0 is reserved for the Celery broker.
    Redis DB 1 is reserved for Celery results.
    Redis DB 2 is reserved for AQE infrastructure and event streams.
    """

    host: str = os.getenv("REDIS_HOST", "redis")

    port: int = int(
        os.getenv("REDIS_PORT", "6379")
    )

    db: int = int(
        os.getenv("REDIS_DB", "2")
    )

    max_connections: int = int(
        os.getenv("REDIS_MAX_CONNECTIONS", "50")
    )

    socket_connect_timeout: float = float(
        os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0")
    )

    socket_timeout: float = float(
        os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")
    )

    health_check_interval: int = int(
        os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")
    )

    retry_on_timeout: bool = _get_bool(
        "REDIS_RETRY_ON_TIMEOUT",
        True,
    )

    @property
    def url(self) -> str:
        """
        Build the Redis connection URL from the configured components.
        """
        return f"redis://{self.host}:{self.port}/{self.db}"


redis_config = RedisConfig()
