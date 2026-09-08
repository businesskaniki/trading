from __future__ import annotations

import logging
from typing import Any

from .client import RedisClient, redis_client
from .exceptions import RedisConnectionError


logger = logging.getLogger(__name__)


class RedisHealthService:
    """
    Provides health and diagnostic information for AQE Redis.
    """

    def __init__(
        self,
        client: RedisClient | None = None,
    ) -> None:
        self.client = client or redis_client

    async def check(self) -> dict[str, Any]:
        """
        Perform a Redis health check.

        Returns:
            Structured health information.
        """
        try:
            ping = await self.client.ping()

            if not ping:
                return {
                    "healthy": False,
                    "redis": False,
                    "error": "Redis did not respond successfully.",
                }

            return {
                "healthy": True,
                "redis": True,
            }

        except RedisConnectionError as exc:
            logger.warning(
                "Redis health check failed: %s",
                exc,
            )

            return {
                "healthy": False,
                "redis": False,
                "error": str(exc),
            }

        except Exception as exc:
            logger.exception(
                "Unexpected Redis health-check failure."
            )

            return {
                "healthy": False,
                "redis": False,
                "error": str(exc),
            }

    async def info(self) -> dict[str, Any]:
        """
        Return Redis server information used for diagnostics.
        """
        return await self.client.info()


redis_health = RedisHealthService()