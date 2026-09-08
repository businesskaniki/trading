from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from .config import RedisConfig, redis_config

logger = logging.getLogger(__name__)


class RedisClientError(Exception):
    """
    Base exception for MT5 Bridge Redis client errors.
    """


class RedisConnectionError(RedisClientError):
    """
    Raised when the bridge cannot connect to Redis.
    """


class RedisClient:
    """
    Async Redis client for the MT5 Bridge.

    The client owns the Redis connection pool and provides
    connection lifecycle management.

    Redis Streams logic is implemented separately.
    """

    def __init__(
        self,
        config: RedisConfig | None = None,
    ) -> None:
        self.config = config or redis_config

        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    @property
    def redis(self) -> Redis:
        """
        Return the active Redis client.

        Raises:
            RedisConnectionError:
                If Redis has not been initialized.
        """
        if self._redis is None:
            raise RedisConnectionError(
                "Redis client has not been initialized. " "Call connect() first."
            )

        return self._redis

    @property
    def is_connected(self) -> bool:
        """
        Return whether Redis is currently initialized.
        """
        return self._redis is not None

    async def connect(self) -> None:
        """
        Initialize the Redis connection pool and verify connectivity.
        """
        if self._redis is not None:
            return

        try:
            self._pool = ConnectionPool.from_url(
                self.config.url,
                max_connections=self.config.max_connections,
                socket_connect_timeout=(self.config.socket_connect_timeout),
                socket_timeout=self.config.socket_timeout,
                health_check_interval=(self.config.health_check_interval),
                retry_on_timeout=self.config.retry_on_timeout,
                decode_responses=True,
            )

            self._redis = Redis(
                connection_pool=self._pool,
            )

            await self._redis.ping()

            logger.info(
                "MT5 Bridge Redis connection established. " "host=%s port=%s db=%s",
                self.config.host,
                self.config.port,
                self.config.db,
            )

        except Exception as exc:
            await self.disconnect()

            logger.exception("Failed to connect MT5 Bridge to Redis.")

            raise RedisConnectionError(
                "Unable to establish a connection to Redis."
            ) from exc

    async def disconnect(self) -> None:
        """
        Close the Redis client and connection pool.

        Safe to call multiple times.
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
                logger.exception("Error while closing Redis connection pool.")

        logger.info("MT5 Bridge Redis connection closed.")

    async def ping(self) -> bool:
        """
        Verify Redis connectivity.
        """
        try:
            response = await self.redis.ping()
        except Exception as exc:
            raise RedisConnectionError("Redis health check failed.") from exc

        return bool(response)

    async def __aenter__(self) -> "RedisClient":
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
