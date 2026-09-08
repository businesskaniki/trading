from __future__ import annotations


class RedisInfrastructureError(Exception):
    """
    Base exception for all AQE Redis infrastructure errors.
    """


class RedisConfigurationError(RedisInfrastructureError):
    """
    Raised when Redis configuration is invalid.
    """


class RedisConnectionError(RedisInfrastructureError):
    """
    Raised when AQE cannot connect to or communicate with Redis.
    """


class RedisOperationError(RedisInfrastructureError):
    """
    Raised when a Redis operation fails.
    """


class RedisSerializationError(RedisOperationError):
    """
    Raised when an event or message cannot be serialized or deserialized.
    """


class RedisStreamError(RedisOperationError):
    """
    Base exception for Redis Streams-related errors.
    """


class RedisStreamNotFoundError(RedisStreamError):
    """
    Raised when a required Redis Stream does not exist.
    """


class RedisConsumerGroupError(RedisStreamError):
    """
    Raised when a Redis Stream consumer group operation fails.
    """


class RedisMessageError(RedisStreamError):
    """
    Raised when a Redis Stream message is invalid or cannot be processed.
    """
