from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from .config import RedisConfig, redis_config
from .exceptions import RedisConnectionError

logger = logging.getLogger(__name__)



class RedisClient:
    """
    Async Redis client for AQE infrastructure.

    This class owns the Redis connection pool and provides the common
    connection lifecycle used by publishers, consumers, and health checks.

    It intentionally does not contain Redis Streams logic. Streams are
    implemented separately so transport concerns remain isolated from
    connection management.
    """

    def __init__(self, config: RedisConfig | None = None) -> None:
        self.config = config or redis_config

        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    @property
    def redis(self) -> Redis:
        """
        Return the active Redis client.

        Raises:
            RedisConnectionError: If the client has not been initialized.
        """
        if self._redis is None:
            raise RedisConnectionError(
                "Redis client has not been initialized. "
                "Call connect() first."
            )

        return self._redis

    @property
    def is_connected(self) -> bool:
        """Return whether the Redis client has been initialized."""
        return self._redis is not None

    async def connect(self) -> None:
        """
        Initialize the Redis connection pool and verify connectivity.

        The connection is verified with PING before the client is considered
        ready. If verification fails, all partially-created resources are
        cleaned up.
        """
        if self._redis is not None:
            return

        try:
            self._pool = ConnectionPool.from_url(
                self.config.url,
                max_connections=self.config.max_connections,
                socket_connect_timeout=self.config.socket_connect_timeout,
                socket_timeout=self.config.socket_timeout,
                health_check_interval=self.config.health_check_interval,
                retry_on_timeout=self.config.retry_on_timeout,
                decode_responses=True,
            )

            self._redis = Redis(connection_pool=self._pool)

            await self._redis.ping()

            logger.info(
                "Redis connection established. url=%s db=%s",
                self.config.url,
                self.config.db,
            )

        except Exception as exc:
            await self.disconnect()

            logger.exception("Failed to connect to Redis.")

            raise RedisConnectionError(
                "Unable to establish a connection to Redis."
            ) from exc

    async def disconnect(self) -> None:
        """
        Close the Redis client and connection pool.

        This method is safe to call multiple times.
        """
        redis = self._redis
        pool = self._pool

        self._redis = None
        self._pool = None

        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                logger.exception("Error while closing Redis client.")

        if pool is not None:
            try:
                await pool.aclose()
            except Exception:
                logger.exception(
                    "Error while closing Redis connection pool."
                )

        logger.info("Redis connection closed.")

    async def ping(self) -> bool:
        """
        Verify that Redis is reachable.

        Returns:
            True when Redis responds successfully.

        Raises:
            RedisConnectionError: If Redis is unavailable.
        """
        try:
            response = await self.redis.ping()
        except Exception as exc:
            raise RedisConnectionError(
                "Redis health check failed."
            ) from exc

        return bool(response)

    async def info(self, section: str | None = None) -> dict[str, Any]:
        """
        Return Redis server information.

        Args:
            section: Optional Redis INFO section, such as ``server``,
                ``memory``, or ``stats``.
        """
        try:
            response = await self.redis.info(section=section)
        except Exception as exc:
            raise RedisConnectionError(
                "Failed to retrieve Redis server information."
            ) from exc

        return dict(response)

    async def __aenter__(self) -> RedisClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.disconnect()


redis_client = RedisClient()