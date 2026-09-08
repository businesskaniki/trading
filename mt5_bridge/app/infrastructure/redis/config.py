from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Explicitly load the MT5 Bridge .env file.
BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def _get_bool(
    name: str,
    default: bool,
) -> bool:
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
    Runtime configuration for MT5 Bridge Redis infrastructure.

    The MT5 Bridge runs directly on the host machine while Redis
    runs inside Docker.

    Therefore the Bridge connects to Redis through the published
    host port:

        localhost:6379
    """

    host: str = os.getenv(
        "REDIS_HOST",
        "localhost",
    )

    port: int = int(
        os.getenv(
            "REDIS_PORT",
            "6379",
        )
    )

    db: int = int(
        os.getenv(
            "REDIS_DB",
            "2",
        )
    )

    max_connections: int = int(
        os.getenv(
            "REDIS_MAX_CONNECTIONS",
            "50",
        )
    )

    socket_connect_timeout: float = float(
        os.getenv(
            "REDIS_SOCKET_CONNECT_TIMEOUT",
            "5",
        )
    )

    socket_timeout: float = float(
        os.getenv(
            "REDIS_SOCKET_TIMEOUT",
            "5",
        )
    )

    health_check_interval: int = int(
        os.getenv(
            "REDIS_HEALTH_CHECK_INTERVAL",
            "30",
        )
    )

    retry_on_timeout: bool = _get_bool(
        "REDIS_RETRY_ON_TIMEOUT",
        True,
    )

    @property
    def url(self) -> str:
        """
        Build the Redis connection URL.
        """
        return (
            f"redis://"
            f"{self.host}:"
            f"{self.port}/"
            f"{self.db}"
        )


redis_config = RedisConfig()